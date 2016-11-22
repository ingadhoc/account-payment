# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, api, _
from openerp.exceptions import ValidationError


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    @api.multi
    def action_account_invoice_payment_group(self):
        self.ensure_one()
        if self.state != 'open':
            raise ValidationError(_(
                'You can only register payment if invoice is open'))
        to_pay_move_lines = self.move_id.line_ids.filtered(
            lambda r: not r.reconciled and r.account_id.internal_type in (
                'payable', 'receivable'))
        # target = 'new'
        # if self.company_id.double_validation:
        #     target = 'current'
        return {
            'name': _('Register Payment'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.payment.group',
            'view_id': False,
            'target': 'current',
            # 'target': target,
            'type': 'ir.actions.act_window',
            # 'domain': [('id', 'in', aml.ids)],
            'context': {
                'to_pay_move_line_ids': to_pay_move_lines.ids,
                'pop_up': True,
            },
        }
