# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, api


class AccountVoucher(models.Model):
    _inherit = "account.voucher"

    @api.multi
    def recompute_voucher_lines(
            self, partner_id, journal_id, price, currency_id, ttype, date):
        """
        Set amount 0 on voucher lines except if invoice_id is send in context
        """
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

    @api.multi
    def onchange_amount(
            self, amount, rate, partner_id, journal_id, currency_id, ttype,
            date, payment_rate_currency_id, company_id):
        """
        Do not refresh lines on amount change
        """
        res = super(AccountVoucher, self).onchange_amount(
            amount, rate, partner_id, journal_id, currency_id, ttype,
            date, payment_rate_currency_id, company_id)
        if self._context.get('invoice_id'):
            return res
        values = res.get('value', {})
        values.pop('line_cr_ids', False)
        values.pop('line_dr_ids', False)
        return res
