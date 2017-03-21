# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountTaxTemplate(models.Model):
    _inherit = "account.tax.template"

    type_tax_use = fields.Selection(
        selection_add=[
            ('customer', 'Customer Payment'),
            ('supplier', 'Supplier Payment'),
        ],
    )


class AccountTax(models.Model):
    """
    We could also use inherits but we should create methods of chart template
    """
    _inherit = "account.tax"

    type_tax_use = fields.Selection(
        selection_add=[
            ('customer', 'Customer Payment'),
            ('supplier', 'Supplier Payment'),
        ],
    )
    amount = fields.Float(
        required=False
    )
    journal_id = fields.Many2one('account.journal', 'Payment Journal')
    sequence_id = fields.Many2one('ir.sequence', 'Sequence') #, required=True
    min_retention_amount = fields.Float(digits=(16, 2), string='Minimum Withholding Amount')

    @api.one
    @api.constrains('journal_id')
    def _check_journal_id(self):
        found = False
        for payment_method in self.journal_id.inbound_payment_method_ids:
            if (payment_method.code == 'withholding'):
                found = True
                break
        
        for payment_method in self.journal_id.outbound_payment_method_ids:
            if (payment_method.code == 'withholding'):
                found = True
                break

        if found == False:
            raise ValidationError(_('Withholding Taxes can only use "Payment Journal" with type "Withholding", please check the data entered.'))