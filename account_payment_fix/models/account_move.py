from odoo import fields, models, api
from odoo.exceptions import UserError

class AccountPaymentAM(models.Model):
    _inherit = "account.move"

    @api.model
    def _get_default_journal(self):
        ''' Get the default journal.
        It could either be passed through the context using the 'default_journal_id' key containing its id,
        either be determined by the default type.
        '''
        move_type = self._context.get('default_move_type', 'entry')
        if move_type in self.get_sale_types(include_receipts=True):
            journal_types = ['sale']
        elif move_type in self.get_purchase_types(include_receipts=True):
            journal_types = ['purchase']
        else:
            journal_types = self._context.get('default_move_journal_types', ['general'])

        if self._context.get('default_journal_id'):
            journal = self.env['account.journal'].browse(self._context['default_journal_id'])

            if move_type != 'entry' and journal.type not in journal_types:
                raise UserError(_(
                    "Cannot create an invoice of type %(move_type)s with a journal having %(journal_type)s as type.",
                    move_type=move_type,
                    journal_type=journal.type,
                ))
        else:
            journal = self._search_default_journal(journal_types)

        return journal

    journal_id = fields.Many2one('account.journal', string='Journal', required=True, readonly=True,
        states={'draft': [('readonly', False)]},
        check_company=True, domain="[('id', 'in', suitable_journal_ids)]",
        tracking=True,
        default=_get_default_journal)