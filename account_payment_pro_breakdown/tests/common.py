##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import Command, fields
from odoo.tests import Form, common


class BreakdownCommon(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.env.user)
        cls.company = cls.env.company
        cls.company.use_payment_pro = True
        if "use_receiptbook" in cls.company._fields:
            # the payment form requires a receipt book, which only some countries enable and create
            cls.company.use_receiptbook = True
            cls.env["account.chart.template"]._create_receiptbooks(cls.company)
        cls.outstanding_account = cls.env["account.account"].search(
            [("company_ids", "=", cls.company.id), ("account_type", "=", "asset_current")], limit=1
        )
        cls.bank_journal = cls.env["account.journal"].create({"name": "Bank BD", "type": "bank", "code": "BNKBD"})
        method_lines = (
            cls.bank_journal.inbound_payment_method_line_ids | cls.bank_journal.outbound_payment_method_line_ids
        )
        for method_line in method_lines.filtered(lambda line: not line.payment_account_id):
            method_line.payment_account_id = cls.outstanding_account
        journal_vals = {}
        if "l10n_latam_use_documents" in cls.env["account.journal"]._fields:
            journal_vals["l10n_latam_use_documents"] = False
        cls.sale_journal = cls.env["account.journal"].create(
            {"name": "Sales BD", "type": "sale", "code": "SALBD", **journal_vals}
        )
        cls.purchase_journal = cls.env["account.journal"].create(
            {"name": "Purchases BD", "type": "purchase", "code": "PURBD", **journal_vals}
        )
        cls.partner = cls.env["res.partner"].create({"name": "Breakdown Partner"})
        cls.currency = cls.company.currency_id
        cls.foreign_currency = cls.env.ref("base.EUR" if cls.currency.name != "EUR" else "base.USD")
        cls.foreign_currency.active = True
        cls.env["res.currency.rate"].search(
            [("currency_id", "=", cls.foreign_currency.id), ("company_id", "=", cls.company.id)]
        ).unlink()

    def _debt(self, amount, move_type="out_invoice", currency=None, date=None):
        """Post an invoice or bill without taxes and return its receivable or payable line."""
        sale = move_type == "out_invoice"
        invoice = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner.id,
                "journal_id": (self.sale_journal if sale else self.purchase_journal).id,
                "invoice_date": date or self.today,
                "date": date or self.today,
                "currency_id": (currency or self.currency).id,
                "invoice_line_ids": [
                    Command.create({"name": "Service", "quantity": 1, "price_unit": amount, "tax_ids": []})
                ],
            }
        )
        invoice.action_post()
        return invoice.line_ids.filtered(
            lambda line: line.account_id.account_type in ("asset_receivable", "liability_payable")
        )

    def _payment(self, amount, debts, payment_type="inbound", **vals):
        return self.env["account.payment"].create(
            {
                "payment_type": payment_type,
                "partner_type": "customer" if payment_type == "inbound" else "supplier",
                "partner_id": self.partner.id,
                "journal_id": self.bank_journal.id,
                "amount": amount,
                "date": self.today,
                "to_pay_move_line_ids": [Command.set(debts.ids)],
                **vals,
            }
        )

    def _break_down(self, payment, amounts):
        """Use the wizard as the web client does."""
        action = payment.action_open_breakdown_wizard()
        wizard_form = Form(self.env[action["res_model"]].with_context(**action["context"]))
        for index, amount in enumerate(amounts):
            with wizard_form.line_ids.edit(index) as line:
                line.amount = amount
        wizard = wizard_form.save()
        wizard.action_confirm()
        return wizard

    def _counterparts(self, payment):
        return payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type in ("asset_receivable", "liability_payable")
        )

    def assertResiduals(self, debts, expected, field="amount_residual"):
        debts.invalidate_recordset(["amount_residual", "amount_residual_currency"])
        self.assertEqual([abs(debt[field]) for debt in debts], expected)
