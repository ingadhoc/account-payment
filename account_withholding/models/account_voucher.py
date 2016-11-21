# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields, api
import openerp.addons.decimal_precision as dp


class account_voucher(models.Model):

    _inherit = "account.voucher"

    withholding_ids = fields.One2many(
        'account.voucher.withholding',
        'voucher_id',
        string='Withholdings',
        required=False,
        readonly=True,
        states={'draft': [('readonly', False)]}
        )
    withholdings_amount = fields.Float(
        'Importe en Retenciones',
        # waiting for a PR 9081 to fix computed fields translations
        # _('Withholdings Amount'),
        help='Importe a ser Pagado con Retenciones',
        # help=_('Amount Paid With Withholdings'),
        compute='_get_withholdings_amount',
        digits=dp.get_precision('Account'),
    )

    @api.one
    @api.depends(
        'withholding_ids.amount',
        )
    def _get_withholdings_amount(self):
        self.withholdings_amount = self.get_withholdings_amount()[self.id]

    @api.depends(
        'withholding_ids.amount',
        )
    def _get_amount(self):
        """Only to Update Depends, should work with paylines amount depends
        but it doesnt so we add it here"""
        return super(account_voucher, self)._get_amount()

    @api.depends(
        'withholdings_amount'
        )
    def _get_paylines_amount(self):
        """Only to Update Depends"""
        return super(account_voucher, self)._get_paylines_amount()

    @api.multi
    def get_withholdings_amount(self):
        res = {}
        for voucher in self:
            withholdings_amount = sum(
                x.amount for x in voucher.withholding_ids)
            res[voucher.id] = withholdings_amount
        return res

    @api.multi
    def get_paylines_amount(self):
        res = super(account_voucher, self).get_paylines_amount()
        for voucher in self:
            withholdings_amount = voucher.get_withholdings_amount()[voucher.id]
            res[voucher.id] = res[voucher.id] + withholdings_amount
        return res

    @api.model
    def paylines_moves_create(
            self, voucher, move_id, company_currency, current_currency):
        paylines_total = super(account_voucher, self).paylines_moves_create(
            voucher, move_id, company_currency, current_currency)
        withholding_total = self.create_withholding_lines(
            voucher, move_id, company_currency, current_currency)
        return paylines_total + withholding_total

    # TODO ver si en vez de usar api.model usamos self y no pasamos el voucher
    # TODO ver que todo esto solo funcione en payment y receipts y no en sale
    # y purchase
    @api.model
    def create_withholding_lines(
            self, voucher, move_id, company_currency, current_currency):
        move_lines = self.env['account.move.line']
        withholding_total = 0.0
        for line in voucher.withholding_ids:
            name = '%s: %s' % (
                line.tax_withholding_id.description, line.internal_number)
            if line.name:
                name += ' (%s)' % line.name
            payment_date = False
            amount = line.amount
            if amount >= 0:
                account = line.tax_withholding_id.account_id
            else:
                account = line.tax_withholding_id.ref_account_id
            partner = voucher.partner_id
            move_line = move_lines.create(
                self.prepare_move_line(
                    voucher, amount, move_id, name, company_currency,
                    current_currency, payment_date, account, partner)
                    )
            line.move_line_id = move_line.id
            move_line.update({
                'tax_code_id': line.tax_withholding_id.tax_code_id.id,
                'tax_amount': amount,
                })
            withholding_total += move_line.debit - move_line.credit
        return withholding_total
