from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    use_receiptbook = fields.Boolean(related="company_id.use_receiptbook")
