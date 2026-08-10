# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestBundleReconcile(TransactionCase):
    """Conciliación de un bundle con una línea de pago en sentido opuesto.

    Caso del ticket 123989: una OP con un pago que excede la deuda más un ajuste por redondeo
    en sentido contrario que la lleva a cero. El super de _reconcile_after_post concilia pago
    por pago contra to_pay_move_line_ids, así que el pago grande cierra toda la deuda y queda
    con residuo, y el ajuste ya no encuentra deuda libre contra la que conciliarse: quedaban
    dos apuntes abiertos que netean cero (conciliación parcial).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True

        bundle_journal_id = cls.company._get_bundle_journal("outbound")
        if bundle_journal_id:
            cls.bundle_journal = cls.env["account.journal"].browse(bundle_journal_id)
        else:
            cls.bundle_journal = cls.env["account.journal"].create(
                {
                    "name": "Payment Bundle",
                    "type": "cash",
                    "code": "PBUND",
                    "company_id": cls.company.id,
                }
            )

        cls.payment_method_bundle = cls.env["account.payment.method"].search([("code", "=", "payment_bundle")], limit=1)
        cls.payment_method_line = cls.env["account.payment.method.line"].search(
            [
                ("journal_id", "=", cls.bundle_journal.id),
                ("payment_method_id", "=", cls.payment_method_bundle.id),
                ("payment_type", "=", "outbound"),
            ],
            limit=1,
        )

        # Diario del pago y diario del ajuste por redondeo: dos diarios de efectivo distintos,
        # como los usa el cliente (Caja Principal Auxiliar + Ajuste por Redondeo).
        cls.cash_journal = cls.env["account.journal"].create(
            {
                "name": "Caja Test",
                "type": "cash",
                "code": "CSHT1",
                "company_id": cls.company.id,
            }
        )
        cls.rounding_journal = cls.env["account.journal"].create(
            {
                "name": "Ajuste por Redondeo Test",
                "type": "cash",
                "code": "ROUND",
                "company_id": cls.company.id,
            }
        )

        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Vendor",
                "vat": "34278580484",
                "country_id": cls.env.ref("base.ar").id,
            }
        )

        cls.purchase_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "purchase")], limit=1
        )

        # Con account_multi_store instalado, su demo asigna a todos los diarios de la compañía un
        # store con only_allow_reonciliaton_of_this_store: los diarios que creamos acá tienen que
        # quedar en el mismo store que la deuda, si no reconcile() rechaza la conciliación.
        if "store_id" in cls.env["account.journal"]._fields:
            (cls.bundle_journal | cls.cash_journal | cls.rounding_journal).store_id = cls.purchase_journal.store_id

    def _create_bill(self, amount):
        bill = self.env["account.move"].create(
            {
                "partner_id": self.partner.id,
                "invoice_date": fields.Date.today(),
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

    def _create_linked_payment(self, main, amount, payment_type, journal):
        return self.env["account.payment"].create(
            {
                "payment_type": payment_type,
                "partner_type": "supplier",
                "partner_id": self.partner.id,
                "journal_id": journal.id,
                "amount": amount,
                "main_payment_id": main.id,
            }
        )

    def test_bundle_with_opposite_sign_rounding_line(self):
        """Pago de 1000.50 + ajuste inbound de 0.50 contra una deuda de 1000."""
        bill = self._create_bill(1000.0)
        debt_line = bill.line_ids.filtered(lambda x: x.account_id.account_type == "liability_payable")

        main = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.partner.id,
                "journal_id": self.bundle_journal.id,
                "payment_method_line_id": self.payment_method_line.id,
                "amount": 0,
                "to_pay_move_line_ids": [Command.set(debt_line.ids)],
            }
        )
        payment = self._create_linked_payment(main, 1000.5, "outbound", self.cash_journal)
        rounding = self._create_linked_payment(main, 0.5, "inbound", self.rounding_journal)

        main.action_post()

        self.assertTrue(debt_line.full_reconcile_id, "La deuda debería quedar totalmente conciliada")
        counterpart_lines = (payment | rounding).move_id.line_ids.filtered(
            lambda x: x.account_id.account_type == "liability_payable"
        )
        self.assertEqual(
            len(counterpart_lines), 2, "Cada pago vinculado debería tener su contrapartida en la cuenta de proveedores"
        )
        for line in counterpart_lines:
            self.assertAlmostEqual(
                line.amount_residual,
                0.0,
                places=2,
                msg=f"{line.move_id.name} quedó con residuo {line.amount_residual}: conciliación parcial",
            )
        self.assertAlmostEqual(
            rounding.matched_amount, 0.5, places=2, msg="El ajuste por redondeo debería quedar imputado"
        )

    def test_bundle_same_sign_lines_still_reconcile(self):
        """Control: dos pagos en el mismo sentido que cierran la deuda exacta siguen conciliando."""
        bill = self._create_bill(1000.0)
        debt_line = bill.line_ids.filtered(lambda x: x.account_id.account_type == "liability_payable")

        main = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.partner.id,
                "journal_id": self.bundle_journal.id,
                "payment_method_line_id": self.payment_method_line.id,
                "amount": 0,
                "to_pay_move_line_ids": [Command.set(debt_line.ids)],
            }
        )
        self._create_linked_payment(main, 999.5, "outbound", self.cash_journal)
        self._create_linked_payment(main, 0.5, "outbound", self.rounding_journal)

        main.action_post()

        self.assertTrue(debt_line.full_reconcile_id, "La deuda debería quedar totalmente conciliada")
        self.assertAlmostEqual(main.unmatched_amount, 0.0, places=2, msg="No debería quedar importe sin imputar")
