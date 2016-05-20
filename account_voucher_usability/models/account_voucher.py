# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, api


class AccountVoucher(models.Model):
    _inherit = "account.voucher"

    @api.multi
    def recompute_voucher_lines(
            self, partner_id, journal_id, price, currency_id, ttype, date):
        default = super(AccountVoucher, self).recompute_voucher_lines(
            partner_id, journal_id, price, currency_id, ttype, date)
        values = default.get('value', {})
        # if we pay from invioce, then we dont clean amount
        if self._context.get('invoice_id'):
            return default
        for val_cr in values.get('line_cr_ids', {}):
            if isinstance(val_cr, dict):
                val_cr.update({'amount': 0.0, 'reconcile': False})
        for val_dr in values.get('line_dr_ids', {}):
            if isinstance(val_dr, dict):
                val_dr.update({'amount': 0.0, 'reconcile': False})
        return default
