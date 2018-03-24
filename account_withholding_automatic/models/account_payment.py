##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields
# import odoo.addons.decimal_precision as dp
# from odoo.exceptions import ValidationError
# from dateutil.relativedelta import relativedelta
# import datetime


class AccountPayment(models.Model):
    _inherit = "account.payment"

    automatic = fields.Boolean(
    )
    withholding_accumulated_payments = fields.Selection(
        related='tax_withholding_id.withholding_accumulated_payments',
        readonly=True,
    )
    withholdable_invoiced_amount = fields.Float(
        'Importe imputado sujeto a retencion',
        # compute='get_withholding_data',
        readonly=True,
    )
    withholdable_advanced_amount = fields.Float(
        'Importe a cuenta sujeto a retencion',
        # compute='get_withholding_data',
        readonly=True,
    )
    accumulated_amount = fields.Float(
        # compute='get_withholding_data',
        readonly=True,
    )
    total_amount = fields.Float(
        # compute='get_withholding_data',
        readonly=True,
    )
    withholding_non_taxable_minimum = fields.Float(
        'Non-taxable Minimum',
        # compute='get_withholding_data',
        readonly=True,
    )
    withholding_non_taxable_amount = fields.Float(
        'Non-taxable Amount',
        # compute='get_withholding_data',
        readonly=True,
    )
    withholdable_base_amount = fields.Float(
        # compute='get_withholding_data',
        readonly=True,
    )
    period_withholding_amount = fields.Float(
        # compute='get_withholding_data',
        readonly=True,
    )
    previous_withholding_amount = fields.Float(
        # compute='get_withholding_data',
        readonly=True,
    )
    computed_withholding_amount = fields.Float(
        # compute='get_withholding_data',
        readonly=True,
    )

    def _get_counterpart_move_line_vals(self, invoice=False):
        vals = super(AccountPayment, self)._get_counterpart_move_line_vals(
            invoice=invoice)
        if self.payment_group_id:
            # we check they are code withholding and we get taxes
            taxes = self.payment_group_id.payment_ids.filtered(
                lambda x: x.payment_method_code == 'withholding').mapped(
                'tax_withholding_id')
            vals['tax_ids'] = [(6, False, taxes.ids)]
        return vals
