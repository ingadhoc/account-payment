from odoo import Command, fields
from odoo.tests import TransactionCase


class PaymentProCommon(TransactionCase):
    """Structural data shared by the account-payment branch test suites.

    Installs the account_payment_pro demo data for the test company and
    exposes the records as class attributes. Downstream modules inherit
    from this class and add their own demo on top. Edge-case records
    belong to each test with .create().
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True
        cls.chart_template = cls.env["account.chart.template"].with_company(cls.company)
        cls.chart_template._install_account_payment_pro_demo(cls.company)
        cls.partner_ri = cls.chart_template.ref("demo_partner_ri")
        cls.product = cls.chart_template.ref("demo_product")
        cls.bank_journal = cls.chart_template.ref("demo_bank_journal")
        cls.sale_journal = cls.chart_template.ref("demo_sale_journal")
        cls.purchase_journal = cls.chart_template.ref("demo_purchase_journal")
        cls._setup_payment_accounts(cls.bank_journal)

    @classmethod
    def _setup_payment_accounts(cls, journal, account=None):
        """Set a payment account on the journal's method lines missing one,
        so posting a payment generates a journal entry right away (without
        it Odoo defers the entry until bank matching)."""
        account = account or cls.env["account.account"].search(
            [("company_ids", "=", cls.company.id), ("account_type", "=", "asset_current")], limit=1
        )
        lines = journal.inbound_payment_method_line_ids + journal.outbound_payment_method_line_ids
        lines.filtered(lambda line: not line.payment_account_id).payment_account_id = account

    def _create_invoice(
        self, move_type="out_invoice", amount=100.0, currency=None, journal=None, partner=None, date=None, post=True
    ):
        """Minimal invoice/refund on the demo journals, posted by default."""
        if journal is None:
            journal = self.purchase_journal if move_type.startswith("in_") else self.sale_journal
        vals = {
            "move_type": move_type,
            "partner_id": (partner or self.partner_ri).id,
            "invoice_date": date or self.today,
            "journal_id": journal.id,
            "company_id": self.company.id,
            "invoice_line_ids": [
                Command.create(
                    {
                        "product_id": self.product.id,
                        "quantity": 1,
                        "price_unit": amount,
                    }
                ),
            ],
        }
        if currency is not None:
            vals["currency_id"] = currency.id
        move = self.env["account.move"].create(vals)
        if post:
            move.action_post()
        return move

    def _get_debt_lines(self, move, account_type=None):
        """Receivable/payable lines of a move (the ones a payment can pay)."""
        account_types = [account_type] if account_type else ["asset_receivable", "liability_payable"]
        return move.line_ids.filtered(lambda line: line.account_id.account_type in account_types)
