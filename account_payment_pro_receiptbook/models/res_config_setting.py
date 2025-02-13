from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    use_receiptbook = fields.Boolean(
        related="company_id.use_receiptbook",
        readonly=False,
    )
