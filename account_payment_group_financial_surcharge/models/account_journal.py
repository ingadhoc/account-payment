##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields


class AccountJournal(models.Model):

    _inherit = "account.journal"

    financing_plan_ids = fields.Many2many(
        'account.financing.plan',
        'account_journal_plans_rel',
        'journal_id',
        'financing_plan_id',
    )
