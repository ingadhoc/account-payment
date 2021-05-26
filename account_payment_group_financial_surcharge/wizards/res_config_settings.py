from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    product_surcharge_id = fields.Many2one(
        related='company_id.product_surcharge_id',
        readonly=False,
    )
