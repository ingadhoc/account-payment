# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import Warning
# from dateutil.relativedelta import relativedelta
# import datetime


class account_voucher_withholding(models.Model):
    _name = "account.voucher.withholding"
    _rec_name = "display_name"
    _description = "Account Withholding Voucher"

    automatic = fields.Boolean(
    )
    voucher_id = fields.Many2one(
        'account.voucher',
        'Voucher',
        required=True,
        ondelete='cascade',
    )
    period_id = fields.Many2one(
        related='voucher_id.period_id',
        store=True,
    )
    display_name = fields.Char(
        compute='get_display_name'
    )
    name = fields.Char(
        'Number',
    )
    description = fields.Char(
    )
    internal_number = fields.Char(
        'Internal Number',
        required=True,
        default='/',
        readonly=True,
        # we add confirmed state for compatibility with double validation
        states={
            'draft': [('readonly', False)],
            'confirmed': [('readonly', False)]
        },
    )
    date = fields.Date(
        'Date',
        required=True,
        default=fields.Date.context_today,
    )
    state = fields.Selection(
        related='voucher_id.state',
        default='draft',
        readonly=True,
    )
    tax_withholding_id = fields.Many2one(
        'account.tax.withholding',
        string='Withholding',
        required=True,
        readonly=True,
        states={
            'draft': [('readonly', False)],
            'confirmed': [('readonly', False)]
        },
    )
    comment = fields.Text(
        'Additional Information',
    )
    base_amount = fields.Float(
        'Base Amount',
        digits=dp.get_precision('Account'),
        readonly=True,
        states={
            'draft': [('readonly', False)],
            'confirmed': [('readonly', False)]
        },
    )
    amount = fields.Float(
        'Amount',
        digits=dp.get_precision('Account'),
        readonly=True,
        states={
            'draft': [('readonly', False)],
            'confirmed': [('readonly', False)]
        },
    )
    move_line_id = fields.Many2one(
        'account.move.line',
        'Journal Item',
        readonly=True,
    )
    # Related fields
    partner_id = fields.Many2one(
        related='voucher_id.partner_id',
        store=True, readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        related='voucher_id.company_id',
        string='Company', store=True, readonly=True
    )
    type = fields.Selection(
        related='voucher_id.type',
        string='Tipo',
        # string='Type',
        # waiting for a PR 9081 to fix computed fields translations
        readonly=True,
        store=True,
    )

    _sql_constraints = [
        ('internal_number_uniq', 'unique(internal_number, tax_withholding_id)',
            'Internal Number must be unique per Tax Withholding!'),
    ]

    @api.one
    @api.depends('name', 'internal_number')
    def get_display_name(self):
        display_name = self.internal_number
        if self.name:
            display_name += ' (%s)' % self.name
        self.display_name = display_name

    @api.one
    @api.constrains('tax_withholding_id', 'voucher_id')
    def check_tax_withholding(self):
        if self.voucher_id.company_id != self.tax_withholding_id.company_id:
            raise Warning(_(
                'Voucher and Tax Withholding must belong to the same company'))

    @api.model
    def create(self, vals):
        if vals.get('internal_number', '/') == '/':
            tax_withholding = self.tax_withholding_id.browse(
                vals.get('tax_withholding_id'))
            if not tax_withholding:
                raise Warning(_('Tax Withholding is Required!'))
            sequence = tax_withholding.sequence_id
            vals['internal_number'] = sequence.next_by_id(sequence.id) or '/'
        return super(account_voucher_withholding, self).create(vals)

    @api.one
    def unlink(self):
        if self.state not in ('draft'):
            raise Warning(_(
                'Only withholding of vouchers on draft state can be deleted!'))
        return super(account_voucher_withholding, self).unlink()
