# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command
from odoo.addons.account_ux.tests.invariants import AccountInvariantsMixin
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestBundleRecomputeOnEdit(AccountInvariantsMixin, TransactionCase):
    """Alta y baja de líneas de medios de pago en un bundle, antes de confirmar.

    FCP-R02: al pagar con dos medios en el mismo comprobante (efectivo + banco), el total
    imputado salía mal — duplicaba una línea o no neteaba. La contrapartida a probar no es
    solo el caso base (que ya no reproduce en 19.0), sino que el usuario edita el bundle
    antes de confirmar: sacar un medio de pago, o sacar una línea de deuda con importes ya
    cargados a mano.

    ``link_payments_total``/``payment_total``/``payment_difference`` viven en
    ``l10n_ar_payment_bundle/models/account_payment.py``: el principal (``is_main_payment``,
    método ``payment_bundle``) nuclea los pagos vinculados (``link_payment_ids``), cada uno
    con su propio diario y monto manual.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True

        bundle_journal_id = cls.company._get_bundle_journal("outbound")
        cls.bundle_journal = cls.env["account.journal"].browse(bundle_journal_id)
        payment_method_bundle = cls.env["account.payment.method"].search([("code", "=", "payment_bundle")], limit=1)
        cls.payment_method_line = cls.env["account.payment.method.line"].search(
            [
                ("journal_id", "=", cls.bundle_journal.id),
                ("payment_method_id", "=", payment_method_bundle.id),
                ("payment_type", "=", "outbound"),
            ],
            limit=1,
        )

        cls.cash_journal = cls.env["account.journal"].create(
            {"name": "Test Bundle Caja", "type": "cash", "code": "TBCA1", "company_id": cls.company.id}
        )
        cls.bank_journal = cls.env["account.journal"].create(
            {"name": "Test Bundle Banco", "type": "bank", "code": "TBBA1", "company_id": cls.company.id}
        )
        cls.cash_manual = cls.cash_journal.outbound_payment_method_line_ids.filtered(
            lambda line: line.payment_method_id.code == "manual"
        )
        cls.bank_manual = cls.bank_journal.outbound_payment_method_line_ids.filtered(
            lambda line: line.payment_method_id.code == "manual"
        )

        cls.purchase_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "purchase")], limit=1
        )
        # mismo store que la deuda (ver test_bundle_reconcile.py), si el módulo está instalado
        if "store_id" in cls.env["account.journal"]._fields:
            (cls.bundle_journal | cls.cash_journal | cls.bank_journal).store_id = cls.purchase_journal.store_id

        cls.vendor = cls.env["res.partner"].create(
            {"name": "Test Bundle Vendor", "vat": "34278580484", "country_id": cls.env.ref("base.ar").id}
        )

    def _create_bill(self, amount):
        bill = self.env["account.move"].create(
            {
                "partner_id": self.vendor.id,
                "invoice_date": "2026-01-01",
                "move_type": "in_invoice",
                "journal_id": self.purchase_journal.id,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.env.ref("product.product_product_16").id,
                            "quantity": 1,
                            "price_unit": amount,
                        }
                    ),
                ],
            }
        )
        bill.action_post()
        return bill

    def _create_main(self, debt_lines):
        return self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.vendor.id,
                "journal_id": self.bundle_journal.id,
                "payment_method_line_id": self.payment_method_line.id,
                "amount": 0,
                "to_pay_move_line_ids": [Command.set(debt_lines.ids)],
            }
        )

    def _create_linked_payment(self, main, amount, journal, method_line):
        return self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.vendor.id,
                "journal_id": journal.id,
                "payment_method_line_id": method_line.id,
                "amount": amount,
                "main_payment_id": main.id,
            }
        )

    def test_two_payment_methods_add_up_without_duplicating(self):
        """Efectivo $20.000 + banco $30.000 sobre una deuda de $50.000: sin duplicar
        liquidez y sin dejar saldo abierto.

        Cubre FCP-R02-E1 (el caso base).
        """
        bill = self._create_bill(50000.0)
        debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        main = self._create_main(debt)
        cash_payment = self._create_linked_payment(main, 20000.0, self.cash_journal, self.cash_manual)
        bank_payment = self._create_linked_payment(main, 30000.0, self.bank_journal, self.bank_manual)

        with self.subTest("el total imputado es el de la deuda, no el doble"):
            self.assertEqual(main.link_payments_total, 50000.0)
            self.assertEqual(main.payment_difference, 0.0)

        main.action_post()
        # el "main" del bundle no tiene asiento propio acá (sin write-off ni
        # retenciones); las invariantes valen sobre los pagos vinculados,
        # que son los que efectivamente asientan.
        for payment in (cash_payment, bank_payment):
            self.assert_payment_invariants(payment, "medio de pago del bundle")
        with self.subTest("cada medio tiene su propia línea de liquidez, sin una tercera por el total"):
            liquidity_lines = (cash_payment.move_id | bank_payment.move_id).line_ids.filtered(
                lambda line: line.account_id.account_type in ("asset_cash", "asset_current", "liability_credit_card")
                and line.account_id != debt.account_id
            )
            self.assertEqual(len(liquidity_lines), 2)
            self.assertEqual(set(liquidity_lines.mapped("balance")), {-20000.0, -30000.0})

        with self.subTest("la factura queda saldada"):
            self.assertEqual(bill.amount_residual, 0.0)

    def test_removing_a_payment_method_line_before_confirming_recomputes_the_total(self):
        """Quitar una línea de medio de pago antes de confirmar: el total baja al valor
        de las líneas restantes, no queda pegado al valor viejo.

        Cubre FCP-R02-E2.
        """
        bill = self._create_bill(50000.0)
        debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        main = self._create_main(debt)
        self._create_linked_payment(main, 20000.0, self.cash_journal, self.cash_manual)
        bank_payment = self._create_linked_payment(main, 30000.0, self.bank_journal, self.bank_manual)
        self.assertEqual(main.link_payments_total, 50000.0)

        main.write({"link_payment_ids": [Command.unlink(bank_payment.id)]})

        self.assertEqual(main.link_payments_total, 20000.0, "recalculado al valor de la línea que queda")
        self.assertEqual(main.payment_difference, 30000.0, "lo que falta cargar para cubrir la deuda")

    def test_removing_a_debt_line_keeps_the_manually_loaded_payment_amounts(self):
        """Quitar una línea de deuda no recalcula a cero los importes ya cargados a
        mano en los medios de pago: la diferencia pasa a saldo a favor.

        Cubre FCP-R02-E3. El bug se manifestaba como "se borró el número que cargué";
        acá se prueba lo contrario, que el número sobrevive y la diferencia se declara.

        No hay una línea de producto que romper para un rojo: la garantía es la
        ausencia de acoplamiento (nada recomputa el ``amount`` de un pago vinculado a
        partir de ``to_pay_move_line_ids`` del principal — ``_onchange_to_pay_lines_
        adjust_amount`` es un ``@api.onchange`` y ni siquiera dispara con ``write()``).
        Esta batería es la guarda para si alguien agrega ese acoplamiento a futuro.
        """
        bill_a = self._create_bill(30000.0)
        bill_b = self._create_bill(20000.0)
        debt_a = bill_a.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        debt_b = bill_b.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        main = self._create_main(debt_a | debt_b)
        cash_payment = self._create_linked_payment(main, 20000.0, self.cash_journal, self.cash_manual)
        bank_payment = self._create_linked_payment(main, 30000.0, self.bank_journal, self.bank_manual)
        self.assertEqual(main.payment_difference, 0.0)

        main.write({"to_pay_move_line_ids": [Command.unlink(debt_b.id)]})

        with self.subTest("los importes cargados a mano no se tocan"):
            self.assertEqual(cash_payment.amount, 20000.0)
            self.assertEqual(bank_payment.amount, 30000.0)

        with self.subTest("la diferencia pasa a saldo a favor, no se recalcula a cero"):
            self.assertEqual(main.to_pay_amount, 30000.0)
            self.assertEqual(main.payment_difference, -20000.0)
