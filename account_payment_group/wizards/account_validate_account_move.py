from odoo import models, _
from odoo.exceptions import UserError


class ValidateAccountMove(models.TransientModel):
    _inherit = "validate.account.move"

    def validate_move(self):
        if self._context.get('active_model') == 'account.move':
            domain = [('id', 'in', self._context.get('active_ids', [])), ('state', '=', 'draft')]
        elif self._context.get('active_model') == 'account.journal':
            domain = [('journal_id', '=', self._context.get('active_id')), ('state', '=', 'draft')]
        else:
            raise UserError(_("Missing 'active_model' in context."))

        moves = self.env['account.move'].search(domain).filtered('line_ids')

        try:
            res = super().validate_move()
        except UserError as error:
            # we consider that an error with "Afip" occurred and we need to pay the invoice with pay now
            if 'AFIP' in repr(error):
                # we try to pay automatic if the pay now journal is setting on the invoice.
                moves.pay_now()
                if not self.env.context.get('l10n_ar_invoice_skip_commit'):
                    self._cr.commit()
            raise UserError(error)
        moves.pay_now()
        return res
