# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, fields, api
# from openerp.exceptions import UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    payment_group_id = fields.Many2one(
        'account.payment.group',
        'Payment Group',
        ondelete='cascade',
    )
    payment_group_company_id = fields.Many2one(
        related='payment_group_id.company_id')
    # we make a copy without transfer option, we try with related but it
    # does not works
    payment_type_copy = fields.Selection(
        selection=[('outbound', 'Send Money'), ('inbound', 'Receive Money')],
        compute='_compute_payment_type_copy',
        inverse='_inverse_payment_type_copy',
        string='Payment Type'
    )

    @api.multi
    @api.onchange('payment_type_copy')
    def _inverse_payment_type_copy(self):
        for rec in self:
            # if false, then it is a transfer
            rec.payment_type = (
                rec.payment_type_copy and rec.payment_type_copy or 'transfer')

    @api.multi
    @api.depends('payment_type')
    def _compute_payment_type_copy(self):
        for rec in self:
            if rec.payment_type == 'transfer':
                continue
            rec.payment_type_copy = rec.payment_type

    @api.onchange('payment_type')
    def _onchange_payment_type(self):
        """
        we disable change of partner_type if we came from a payment_group
        """
        if self._context.get('payment_group'):
            # Set payment method domain
            res = self._onchange_journal()
            if not res.get('domain', {}):
                res['domain'] = {}
            res['domain']['journal_id'] = self.payment_type == 'inbound' and [
                ('at_least_one_inbound', '=', True),
                ('company_id', '=', self.payment_group_company_id.id)] or [
                ('at_least_one_outbound', '=', True),
                ('company_id', '=', self.payment_group_company_id.id)]
            res['domain']['journal_id'].append(
                ('type', 'in', ('bank', 'cash')))
            return res
        return super(AccountPayment, self)._onchange_payment_type()
