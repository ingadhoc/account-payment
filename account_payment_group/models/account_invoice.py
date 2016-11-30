# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, api, fields, _
from openerp.exceptions import ValidationError


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    open_move_line_ids = fields.One2many(
        'account.move.line',
        compute='_compute_open_move_lines'
    )

    @api.multi
    def _get_tax_factor(self):
        self.ensure_one()
        return (self.amount_total and (
            self.amount_untaxed / self.amount_total) or 1.0)

    @api.multi
    def _compute_open_move_lines(self):
        for rec in self:
            rec.open_move_line_ids = rec.move_id.line_ids.filtered(
                lambda r: not r.reconciled and r.account_id.internal_type in (
                    'payable', 'receivable'))

    @api.multi
    def action_account_invoice_payment_group(self):
        self.ensure_one()
        if self.state != 'open':
            raise ValidationError(_(
                'You can only register payment if invoice is open'))
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
                'to_pay_move_line_ids': self.open_move_line_ids.ids,
                'pop_up': True,
            },
        }
