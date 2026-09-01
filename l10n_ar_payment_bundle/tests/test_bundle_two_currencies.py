# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command
from odoo.addons.account_ux.tests.invariants import AccountInvariantsMixin
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestBundleTwoCurrencies(AccountInvariantsMixin, TransactionCase):
    """Medios de pago de un bundle en dos monedas distintas.

    FCP-R02-E5: banco USD 20 (TC 1.000) + efectivo ARS $30.000 sobre una deuda de $50.000 —
    la conversión tiene que hacerse una sola vez, sin dejar una diferencia de cambio espuria
    por partida doble (una vez al convertir el medio, otra al comparar contra la deuda).

    No cubre FCP-R02-E4 (cuatro medios: efectivo + banco + cheque de terceros nuevo +
    cheque en cartera). **Investigado y queda sin implementar**: el mecanismo que la
    spec describe no existe tal cual en 19.0. ``new_third_party_checks`` (crear un
    cheque de terceros nuevo dentro del mismo pago) es un método **solo de cobro**
    (``payment_type == "inbound"``, confirmado en shell) — no hay línea de pago
    saliente que cree un cheque de terceros nuevo. La única vía para pagar con un
    cheque de terceros es ``out_third_party_checks``, y esa espera un cheque **ya
    en cartera** (seleccionado por ``l10n_latam_check_ids``, no creado por
    ``l10n_latam_new_check_ids`` — probado en shell: escribir el nuevo cheque ahí
    deja el sub-pago en $0). El bundle con "cheque de terceros nuevo + cheque en
    cartera" que describe la spec parece asumir una combinación que no está
    disponible en el módulo base (``l10n_latam_check``, la única dependencia de
    cheques que tiene este módulo — ``l10n_latam_check_ux`` no es dependencia).
    Reportado aparte para validar con quien escribió la spec si el escenario real
    era otro (por ejemplo dos cheques ya en cartera).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # env.company en esta base es una compañía demo en USD (no ARS) — la moneda
        # de la compañía tiene que ser distinta a la del medio "extranjero" del test,
        # así que resolvemos una compañía AR real (mismo patrón que l10n_ar_tax).
        cls.company = cls.env["res.company"].search(
            [("l10n_ar_tax_base_account_id", "!=", False), ("partner_id.country_id.code", "=", "AR")], limit=1
        )
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        cls.env.user.company_id = cls.company
        cls.company.use_payment_pro = True

        cls.usd = cls.env.ref("base.USD")
        cls.usd.active = True
        cls.env["res.currency.rate"].create(
            {"currency_id": cls.usd.id, "company_id": cls.company.id, "name": "2026-01-01", "rate": 0.001}
        )

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
            {"name": "Test Bundle Caja Dos Monedas", "type": "cash", "code": "TBCA2", "company_id": cls.company.id}
        )
        cls.usd_bank_journal = cls.env["account.journal"].create(
            {
                "name": "Test Bundle Banco USD",
                "type": "bank",
                "code": "TBBU1",
                "currency_id": cls.usd.id,
                "company_id": cls.company.id,
            }
        )
        cls.cash_manual = cls.cash_journal.outbound_payment_method_line_ids.filtered(
            lambda line: line.payment_method_id.code == "manual"
        )
        cls.usd_bank_manual = cls.usd_bank_journal.outbound_payment_method_line_ids.filtered(
            lambda line: line.payment_method_id.code == "manual"
        )

        cls.purchase_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "purchase")], limit=1
        )
        if "store_id" in cls.env["account.journal"]._fields:
            (cls.bundle_journal | cls.cash_journal | cls.usd_bank_journal).store_id = cls.purchase_journal.store_id

        cls.invoice_a = cls.env.ref("l10n_ar.dc_a_f")
        cls.vendor = cls.env["res.partner"].create(
            {
                "name": "Test Bundle Two Currencies Vendor",
                "company_id": False,
                "l10n_latam_identification_type_id": cls.env.ref("l10n_ar.it_cuit").id,
                "l10n_ar_afip_responsibility_type_id": cls.env.ref("l10n_ar.res_IVARI").id,
                "vat": "30710158267",
            }
        )

    def test_two_currencies_convert_once_without_spurious_exchange_difference(self):
        """Efectivo ARS $30.000 + banco USD 20 (a $1.000) sobre una deuda de $50.000:
        el total imputado es exactamente $50.000, sin una línea de diferencia de cambio
        de más — la conversión de los USD pasa una sola vez, no dos.
        """
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
                "l10n_latam_document_number": "1-1000",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Test bundle two currencies bill line",
                            "quantity": 1,
                            "price_unit": 50000.0,
                            "account_id": expense.id,
                            "tax_ids": [Command.clear()],
                        }
                    ),
                ],
            }
        )
        bill.action_post()
        debt = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")

        main = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.vendor.id,
                "journal_id": self.bundle_journal.id,
                "payment_method_line_id": self.payment_method_line.id,
                "amount": 0,
                "to_pay_move_line_ids": [Command.set(debt.ids)],
            }
        )
        cash_payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.vendor.id,
                "journal_id": self.cash_journal.id,
                "payment_method_line_id": self.cash_manual.id,
                "amount": 30000.0,
                "main_payment_id": main.id,
            }
        )
        usd_payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.vendor.id,
                "journal_id": self.usd_bank_journal.id,
                "payment_method_line_id": self.usd_bank_manual.id,
                "amount": 20.0,
                "date": "2026-01-01",
                "main_payment_id": main.id,
            }
        )

        with self.subTest("el total imputado es exactamente la deuda, conversión hecha una sola vez"):
            self.assertEqual(main.link_payments_total, 50000.0)
            self.assertEqual(main.payment_difference, 0.0)

        main.action_post()
        # el "main" del bundle no tiene asiento propio acá (sin write-off ni
        # retenciones); las invariantes valen sobre los pagos vinculados.
        for payment in (cash_payment, usd_payment):
            self.assert_payment_invariants(payment, "medio de pago del bundle en dos monedas")
        with self.subTest("sin diferencia de cambio espuria: solo hay las dos líneas de liquidez esperadas"):
            liquidity_lines = (cash_payment.move_id | usd_payment.move_id).line_ids.filtered(
                lambda line: line.account_id != debt.account_id
            )
            self.assertEqual(len(liquidity_lines), 2)
            self.assertEqual(self.company.currency_id.round(sum(liquidity_lines.mapped("balance"))), -50000.0)

        with self.subTest("la factura queda saldada"):
            self.assertEqual(bill.amount_residual, 0.0)
