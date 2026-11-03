##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import Command, fields
from odoo.tests import common


class EarlyDiscountCommon(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True
        if "use_receiptbook" in cls.company._fields:
            # the payment form requires a receipt book, which only some countries enable and create
            cls.company.use_receiptbook = True
            cls.env["account.chart.template"]._create_receiptbooks(cls.company)
        cls.bank_journal = cls.env["account.journal"].create({"name": "Bank ED", "type": "bank", "code": "BNKED"})
        outstanding_account = cls.env["account.account"].search(
            [("company_ids", "=", cls.company.id), ("account_type", "=", "asset_current")], limit=1
        )
        for pml in cls.bank_journal.inbound_payment_method_line_ids.filtered(lambda x: not x.payment_account_id):
            pml.payment_account_id = outstanding_account
        sale_vals = {"name": "Sales ED", "type": "sale", "code": "SALED"}
        if "l10n_latam_use_documents" in cls.env["account.journal"]._fields:
            sale_vals["l10n_latam_use_documents"] = False
        cls.sale_journal = cls.env["account.journal"].create(sale_vals)
        cls.partner = cls.env["res.partner"].create({"name": "Early Discount Partner"})
        cls.payment_term = cls.env["account.payment.term"].create(
            {
                "name": "30 days, 5% if paid within 10 days",
                "early_discount": True,
                "discount_percentage": 5,
                "discount_days": 10,
                "early_pay_discount_computation": "included",
                "line_ids": [Command.create({"value": "percent", "value_amount": 100, "nb_days": 30})],
            }
        )

    def _create_invoice(self, invoice_date, lines=None, **vals):
        lines = lines or [{"name": "Service", "quantity": 1, "price_unit": 1000}]
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "journal_id": self.sale_journal.id,
                "invoice_date": invoice_date,
                "invoice_payment_term_id": self.payment_term.id,
                "invoice_line_ids": [Command.create(line) for line in lines],
                **vals,
            }
        )
        invoice.action_post()
        return invoice

    def _pay(self, invoice, amount, date):
        context = invoice.action_register_payment()["context"]
        payment = (
            self.env["account.payment"]
            .with_context(**context)
            .create({"journal_id": self.bank_journal.id, "amount": amount, "date": date})
        )
        residual = invoice.amount_residual
        payment.action_post()
        self.assertTrue(invoice.currency_id.compare_amounts(invoice.amount_residual, residual - amount) == 0)
        return payment

    def _discounted_total(self, invoice):
        term_line = invoice.line_ids.filtered(lambda line: line.display_type == "payment_term")
        return term_line.discount_amount_currency
