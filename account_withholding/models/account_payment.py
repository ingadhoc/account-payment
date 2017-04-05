# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields, api, _
from openerp.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    tax_withholding_id = fields.Many2one(
        'account.tax',
        string='Withholding Tax',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    withholding_number = fields.Char(
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    withholding_base_amount = fields.Monetary(
        string='Withholding Base Amount',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )

    def _get_liquidity_move_line_vals(self, amount):
        vals = super(AccountPayment, self)._get_liquidity_move_line_vals(
            amount)
        if self.payment_method_code == 'withholding':
            if self.payment_type == 'transfer':
                raise UserError(_(
                    'You can not use withholdings on transfers!'))
            if (
                    (self.partner_type == 'customer' and
                        self.payment_type == 'inbound') or
                    (self.partner_type == 'supplier' and
                        self.payment_type == 'outbound')):
                account = self.tax_withholding_id.account_id
            else:
                account = self.tax_withholding_id.refund_account_id
            # if not accounts on taxes then we use accounts of journal
            if account:
                vals['account_id'] = account.id
            vals['name'] = self.withholding_number or '/'
            vals['tax_line_id'] = self.tax_withholding_id.id
            # if not account:
            #     raise UserError(_(
            #         'Accounts not configured on tax %s' % (
            #             self.tax_withholding_id.name)))
        return vals

    @api.one
    def post(self):
        res = super(AccountPayment, self).post()
        for payment in self:
            if payment.payment_method_code == 'withholding':
                sequence = payment.tax_withholding_id.sequence_id
                if sequence:
                    next_number = sequence.number_next_actual
                    self.withholding_number = sequence.get_next_char(next_number)
                    payment.tax_withholding_id.sequence_id.write({'number_next_actual': sequence.number_next_actual + sequence.number_increment})
        return res
