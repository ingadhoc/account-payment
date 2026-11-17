# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestBundlePartnerChange(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True

        bundle_journal_id = cls.company._get_bundle_journal("inbound")
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
        cls.payment_method_line = cls.env["account.payment.method.line"].search(
            [
                ("journal_id", "=", cls.bundle_journal.id),
                ("payment_method_id.code", "=", "payment_bundle"),
                ("payment_type", "=", "inbound"),
            ],
            limit=1,
        )
        cls.cash_journal = cls.env["account.journal"].create(
            {
                "name": "Caja Test",
                "type": "cash",
                "code": "CSHT1",
                "company_id": cls.company.id,
            }
        )
        cls.cash_journal_2 = cls.env["account.journal"].create(
            {
                "name": "Caja Test 2",
                "type": "cash",
                "code": "CSHT2",
                "company_id": cls.company.id,
            }
        )
        cls.sale_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "sale")], limit=1
        )
        # account_multi_store demo restricts reconciliation to the journal store
        if "store_id" in cls.env["account.journal"]._fields:
            (cls.bundle_journal | cls.cash_journal | cls.cash_journal_2).store_id = cls.sale_journal.store_id

        cls.product = cls.env["product.product"].create({"name": "Servicio Test", "type": "service"})
        cls.partner_a, cls.partner_b = cls.env["res.partner"].create(
            [
                {"name": "Cliente A", "vat": "34278580484", "country_id": cls.env.ref("base.ar").id},
                {"name": "Cliente B", "vat": "20222222223", "country_id": cls.env.ref("base.ar").id},
            ]
        )

    def _debt_line(self, partner, amount):
        invoice = self.env["account.move"].create(
            {
                "partner_id": partner.id,
                "invoice_date": fields.Date.today(),
                "move_type": "out_invoice",
                "journal_id": self.sale_journal.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        }
                    ),
                ],
            }
        )
        invoice.action_post()
        return invoice.line_ids.filtered(lambda x: x.account_id.account_type == "asset_receivable")

    def _check_partner_change_after_reset_to_draft(self, amounts_per_journal):
        debt_a = self._debt_line(self.partner_a, 1000.0)
        debt_b = self._debt_line(self.partner_b, 1000.0)
        main = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_a.id,
                "journal_id": self.bundle_journal.id,
                "payment_method_line_id": self.payment_method_line.id,
                "amount": 0,
                "to_pay_move_line_ids": [Command.set(debt_a.ids)],
            }
        )
        linked = self.env["account.payment"].create(
            [
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "journal_id": journal.id,
                    "amount": amount,
                    "main_payment_id": main.id,
                }
                for journal, amount in amounts_per_journal
            ]
        )
        main.action_post()
        main.action_draft()

        main.write({"partner_id": self.partner_b.id, "to_pay_move_line_ids": [Command.set(debt_b.ids)]})
        main.action_post()

        self.assertEqual(linked.partner_id, self.partner_b)
        self.assertEqual(linked.move_id.line_ids.partner_id, self.partner_b)
        self.assertTrue(debt_b.reconciled)
        self.assertFalse(debt_a.reconciled)

    def test_change_partner_after_reset_to_draft(self):
        """Changing the receipt partner after reset to draft moves the linked payment entry to the new partner."""
        self._check_partner_change_after_reset_to_draft([(self.cash_journal, 1000.0)])

    def test_change_partner_after_reset_to_draft_two_linked_payments(self):
        """Same as above with two linked payments: every linked entry moves to the new partner."""
        self._check_partner_change_after_reset_to_draft([(self.cash_journal, 600.0), (self.cash_journal_2, 400.0)])
