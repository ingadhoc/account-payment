# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, api, fields


class AccountPaymentGroup(models.Model):

    _inherit = "account.payment.group"

    withholdings_amount = fields.Monetary(
        compute='_compute_withholdings_amount'
    )

    @api.multi
    @api.depends(
        'payment_ids.tax_withholding_id',
        'payment_ids.amount',
    )
    def _compute_withholdings_amount(self):
        for rec in self:
            rec.withholdings_amount = sum(
                rec.payment_ids.filtered(
                    lambda x: x.tax_withholding_id).mapped('amount'))

    @api.multi
    def compute_withholdings(self):
        for rec in self:
            if rec.partner_type != 'supplier':
                continue
            self.env['account.tax'].search([
                ('type_tax_use', '=', rec.partner_type),
                ('company_id', '=', rec.company_id.id),
            ]).create_payment_withholdings(rec)

    @api.multi
    def confirm(self):
        res = super(AccountPaymentGroup, self).confirm()
        for rec in self:
            if rec.company_id.automatic_withholdings:
                rec.compute_withholdings()
        return res
