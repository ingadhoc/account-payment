##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields


class AccountJournal(models.Model):

    _inherit = "account.journal"

    available_card_ids = fields.Many2many(
        'account.card',
        'account_journal_card_rel',
        'journal_id',
        'card_id',
        string='Cards',
    )

