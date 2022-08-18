##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields


class ResCompany(models.Model):

    _inherit = 'res.company'

    product_surcharge_id = fields.Many2one(
        'product.product',
        'Product for use in financial surcharge'
    )
