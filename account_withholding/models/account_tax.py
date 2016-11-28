# -*- coding: utf-8 -*-
from openerp import models, fields


class AccountTaxTemplate(models.Model):
    _inherit = "account.tax.template"

    type_tax_use = fields.Selection(
        selection_add=[
            ('customer', 'Customer Payment'),
            ('supplier', 'Supplier Payment'),
        ],
    )


class AccountTax(models.Model):
    _inherit = "account.tax"

    type_tax_use = fields.Selection(
        selection_add=[
            ('customer', 'Customer Payment'),
            ('supplier', 'Supplier Payment'),
        ],
    )
