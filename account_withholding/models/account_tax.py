from odoo import models, fields


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
    withholding_sequence_id = fields.Many2one(
        'ir.sequence',
        'Withholding Number Sequence',
        domain=[('code', '=', 'account.tax.withholding')],
        context=(
            "{'default_code': 'account.tax.withholding',"
            " 'default_name': name}"),
        help='If no sequence provided then it will be required for you to'
             ' enter withholding number when registering one.',
        # 'default_prefix': 'x-', 'default_padding': 8}",
        copy=False
    )
