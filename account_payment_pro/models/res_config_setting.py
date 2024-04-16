from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    double_validation = fields.Boolean(
        related='company_id.double_validation',
        readonly=False,
    )
