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
        if not res or self._context.get('invoice_id'):
            return res
        values = res.get('value', {})
        values.pop('line_cr_ids', False)
        values.pop('line_dr_ids', False)
        return res

    # no modificamos esta porque es la que se usa en los receipts que no usamos
    # onchange_journal_voucher

    # desactivamos esto que era para que no se actualicen las lineas porque
    # la funcion de abajo, que deberia actualizar si cambia la moneda, no nos
    # funciona
    # tal vez podriamos mandar la moneda por aca y saber si esta cambiando o no
    # y en funcion a eso actualizar o no
    @api.multi
    def onchange_journal(
            self, journal_id, line_ids, tax_id, partner_id, date, amount,
            ttype, company_id):
        if not journal_id:
            return False
        res = super(AccountVoucher, self).onchange_journal(
            journal_id, line_ids, tax_id, partner_id, date, amount, ttype,
            company_id)
        # we only clean lines if currency is the same
        context = dict(self.env.context)
        currency_id = context.get('currency_id', False)
        journal = self.env['account.journal'].browse(journal_id)
        new_currency = journal.currency or journal.company_id.currency_id
        if currency_id and new_currency.id == currency_id:
            values = res.get('value', {})
            values.pop('line_cr_ids', False)
            values.pop('line_dr_ids', False)
        return res

    # Esto lo dejamos porque lo usamos antes para tener una actualizacion
    # manual pero al final la borramos
    # la desactivbo por ahora porque algunas veces duplica lineas
    # @api.multi
    # @api.onchange('currency_id', 'company_id')
    # def refresh_lines(self):
    #     self.ensure_one()
    #     res = self.with_context(currency_changed=True).onchange_journal(
    #         self.journal_id.id, [], False, self.partner_id.id,
    #         self.date, self.amount, self.type, self.company_id.id)
    #     values = res.get('value', {})
    #     # we do this way because return res didint change values
    #     for key, value in values.iteritems():
    #         setattr(self, key, value)
    #     return res

    # desactivamos porque si no hacemos andar la anterior entonces no
    # tiene sentido
    # @api.multi
    # def action_refresh_lines(self):
    #     self.ensure_one()
    #     self.line_ids.unlink()
    #     res = self.recompute_voucher_lines(
    #         self.partner_id.id, self.journal_id.id,
    #         self.amount, self.currency_id.id, self.type, self.date)
    #     values = res.get('value', {})
    #     values.pop('pre_line')
    #     for key, value in values.iteritems():
    #         if key in ('line_cr_ids', 'line_dr_ids'):
    #             for item in value:
    #                 item['voucher_id'] = self.id
    #                 self.line_ids.create(item)
    #         else:
    #             self.write({key: value})
