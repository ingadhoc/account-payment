# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, api


class AccountVoucher(models.Model):

    _inherit = "account.voucher"

    @api.multi
    def compute_withholdings(self):
        for voucher in self:
            self.env['account.tax.withholding'].search([
                ('type_tax_use', 'in', [self.type, 'all']),
                ('company_id', '=', self.company_id.id),
            ]).create_voucher_withholdings(voucher)

    @api.multi
    def action_confirm(self):
        res = super(AccountVoucher, self).action_confirm()
        self.search([
            ('type', '=', 'payment'),
            ('journal_id.automatic_withholdings', '=', True),
            ('id', 'in', self.ids),
        ]).compute_withholdings()
        return res
