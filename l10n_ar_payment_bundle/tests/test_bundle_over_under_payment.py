# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestBundleOverUnderPayment(TransactionCase):
    """Un bundle que paga de menos, de más, o sin deuda seleccionada.

    FCP-R02-E6/E7/E8: los medios de pago no tienen por qué sumar exactamente la deuda
    seleccionada — pagar de menos no dispara un write-off automático (D9: el ajuste lo
    carga el usuario) y pagar de más no bloquea (D8: el excedente queda a cuenta del
    partner, sin imputarse solo a otras facturas).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].search(
            [("l10n_ar_tax_base_account_id", "!=", False), ("partner_id.country_id.code", "=", "AR")], limit=1
        )
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        cls.env.user.company_id = cls.company
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
            {"name": "Test Bundle Caja Over Under", "type": "cash", "code": "TBCA3", "company_id": cls.company.id}
        )
        cls.bank_journal = cls.env["account.journal"].create(
            {"name": "Test Bundle Banco Over Under", "type": "bank", "code": "TBBA3", "company_id": cls.company.id}
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
        if "store_id" in cls.env["account.journal"]._fields:
            (cls.bundle_journal | cls.cash_journal | cls.bank_journal).store_id = cls.purchase_journal.store_id

        cls.invoice_a = cls.env.ref("l10n_ar.dc_a_f")
        cls.vendor = cls.env["res.partner"].create(
            {
                "name": "Test Bundle Over Under Vendor",
                "company_id": False,
                "l10n_latam_identification_type_id": cls.env.ref("l10n_ar.it_cuit").id,
                "l10n_ar_afip_responsibility_type_id": cls.env.ref("l10n_ar.res_IVARI").id,
                "vat": "30710158270",
            }
        )

    def _create_bill(self, amount, document_number):
        expense = self.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "=", self.company.id)], limit=1
        )
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor.id,
                "invoice_date": "2026-01-01",
                "company_id": self.company.id,
                "l10n_latam_document_type_id": self.invoice_a.id,
                "l10n_latam_document_number": document_number,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Test bundle over/under bill line",
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": expense.id,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        bill.action_post()
        return bill

    def _create_main(self, debt_lines=None):
        """Sin ``debt_lines``, arma un pago a cuenta explícito.

        ``to_pay_move_line_ids`` es un compute que se autocompleta con TODA la deuda
        abierta del partner apenas se crea un pago con ``use_payment_pro`` (mismo
        comportamiento que el formulario real al elegir un partner con deuda) — omitir
        la clave en el ``create`` no alcanza para representar "a cuenta": hay que
        vaciarla a propósito, como hace el usuario con el botón "Quitar todo".
        """
        vals = {
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": self.vendor.id,
            "journal_id": self.bundle_journal.id,
            "payment_method_line_id": self.payment_method_line.id,
            "amount": 0,
            "to_pay_move_line_ids": [Command.set(debt_lines.ids) if debt_lines is not None else Command.clear()],
        }
        return self.env["account.payment"].create(vals)

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

    def test_paying_less_than_the_debt_leaves_it_partial_without_an_automatic_write_off(self):
        """Efectivo $20.000 + banco $20.000 sobre una deuda de $50.000: la diferencia de
        $10.000 queda declarada (no absorbida por un write-off que nadie pidió) y la
        factura queda en pago parcial con ese saldo.

        Cubre FCP-R02-E6.
        """
        bill = self._create_bill(50000.0, "1-1100")
        debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        main = self._create_main(debt)
        self._create_linked_payment(main, 20000.0, self.cash_journal, self.cash_manual)
        self._create_linked_payment(main, 20000.0, self.bank_journal, self.bank_manual)

        with self.subTest("la diferencia queda declarada, sin write-off automático"):
            self.assertEqual(main.payment_difference, 10000.0)
            self.assertEqual(main.write_off_amount, 0.0)

        main.action_post()
        with self.subTest("la factura queda en pago parcial con el saldo declarado"):
            self.assertEqual(bill.payment_state, "partial")
            self.assertEqual(bill.amount_residual, 10000.0)

    def test_paying_more_than_the_debt_becomes_credit_without_touching_other_bills(self):
        """Efectivo $30.000 + banco $30.000 sobre una deuda de $50.000: no bloquea (D8),
        el excedente de $10.000 queda a cuenta del partner, y una factura vieja del
        mismo proveedor NO se toca — el exceso no se autoimputa a la deuda más antigua.

        Cubre FCP-R02-E7.
        """
        old_bill = self._create_bill(15000.0, "1-1101")
        bill = self._create_bill(50000.0, "1-1102")
        debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")
        main = self._create_main(debt)
        self._create_linked_payment(main, 30000.0, self.cash_journal, self.cash_manual)
        self._create_linked_payment(main, 30000.0, self.bank_journal, self.bank_manual)

        with self.subTest("el excedente queda como saldo a favor, sin bloquear"):
            self.assertEqual(main.payment_difference, -10000.0)

        main.action_post()
        with self.subTest("la factura seleccionada queda saldada"):
            self.assertEqual(bill.amount_residual, 0.0)
        with self.subTest("una factura vieja sin relación con este pago no se toca"):
            self.assertEqual(old_bill.payment_state, "not_paid")
            self.assertEqual(old_bill.amount_residual, 15000.0)

    def test_payment_on_account_without_debt_selected_does_not_auto_reconcile_old_debt(self):
        """Un bundle a cuenta (``to_pay_move_line_ids`` vacío a propósito) con dos
        medios de pago postea sin exigir deuda, y una factura vieja sin relación con
        este pago NO se toca — el pago queda como saldo a favor, no autoimputado.

        Cubre FCP-R02-E8. Primer intento de este test (sin vaciar
        ``to_pay_move_line_ids`` a propósito) parecía reproducir el bug que describe
        el escenario: la factura vieja quedaba conciliada igual. Investigado a fondo
        (ver ``_compute_to_pay_move_lines`` en ``account_payment_pro``), no es un bug:
        ese campo se autocompleta con toda la deuda abierta del partner apenas se crea
        el pago — mismo comportamiento que el formulario real — y omitir la clave en
        el ``create`` no representa "a cuenta"; hay que vaciarla a propósito. Con eso
        hecho, el mecanismo ya funciona bien: no hace falta ningún fix de producto.
        """
        old_bill = self._create_bill(15000.0, "1-1103")
        main = self._create_main()
        self._create_linked_payment(main, 25000.0, self.cash_journal, self.cash_manual)
        self._create_linked_payment(main, 25000.0, self.bank_journal, self.bank_manual)

        main.action_post()

        with self.subTest("el pago a cuenta postea sin exigir deuda"):
            self.assertEqual(main.state, "paid")
        with self.subTest("una factura vieja sin relación con este pago no se toca"):
            self.assertEqual(old_bill.payment_state, "not_paid")
            self.assertEqual(old_bill.amount_residual, 15000.0)
