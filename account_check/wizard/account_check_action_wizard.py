# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import api, fields, models, _
from openerp.exceptions import ValidationError


class AccountCheckActionWizard(models.TransientModel):
    _name = 'account.check.action.wizard'
    _description = 'Account Check Action Wizard'

    date = fields.Date(
        default=fields.Date.context_today,
        required=True,
    )
    action_type = fields.Char(
        'Action type passed on the context',
        required=True,
    )

    @api.multi
    def action_confirm(self):
        self.ensure_one()
        if self.action_type not in [
                'claim', 'bank_debit', 'reject', 'customer_return']:
            raise ValidationError(_(
                'Action %s not supported on checks') % self.action_type)
        check = self.env['account.check'].browse(
            self._context.get('active_id'))
        return getattr(
            check.with_context(action_date=self.date), self.action_type)()
