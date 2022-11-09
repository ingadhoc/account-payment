from odoo import models, fields, api
from odoo.addons.account.models.account_tax import TYPE_TAX_USE


TYPE_TAX_USE += [('customer', 'Customer Payment'), ('supplier', 'Supplier Payment')]


class AccountTax(models.Model):
    """
    We could also use inherits but we should create methods of chart template
    """
    _inherit = "account.tax"

    amount = fields.Float(
        default=0.0,
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

    @api.model_create_multi
    def create(self, vals_list):
        recs = super(AccountTax, self).create(vals_list)
        for tax in recs.filtered(lambda x: x.type_tax_use == 'supplier' and not x.withholding_sequence_id):
            tax.withholding_sequence_id = self.withholding_sequence_id.sudo().create({
                'name': tax.name,
                'implementation': 'no_gap',
                # 'prefix': False,
                'padding': 8,
                'number_increment': 1,
                'code': 'account.tax.withholding',
                'company_id': tax.company_id.id,
            }).id
        return recs
