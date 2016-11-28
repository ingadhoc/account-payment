# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, api


class AccountPaymentGroup(models.Model):

    _inherit = "account.payment.group"

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
