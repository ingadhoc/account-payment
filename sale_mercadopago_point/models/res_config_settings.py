from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mp_point_access_token = fields.Char(
        related="company_id.mp_point_access_token",
        readonly=False,
        help="MercadoPago Point Access Token for API authentication.",
    )

    mp_point_client_id = fields.Char(
        related="company_id.mp_point_client_id",
        readonly=False,
        help="MercadoPago Point Client ID for API authentication.",
    )

    mp_point_client_secret = fields.Char(
        related="company_id.mp_point_client_secret",
        readonly=False,
        help="MercadoPago Point Client Secret for API authentication.",
    )

    mp_point_sandbox_mode = fields.Boolean(
        related="company_id.mp_point_sandbox_mode",
        readonly=False,
        help="Enable sandbox mode for MercadoPago Point testing.",
    )
