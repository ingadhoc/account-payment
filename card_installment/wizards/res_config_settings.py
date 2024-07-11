##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    product_surcharge_id = fields.Many2one(
        related='company_id.product_surcharge_id',
        readonly=False,
    )
