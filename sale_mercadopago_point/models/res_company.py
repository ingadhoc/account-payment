from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    # MercadoPago Point API Configuration
    mp_point_access_token = fields.Char(
        string='MercadoPago Access Token',
        help='Access token for MercadoPago Point API'
    )
    mp_point_client_id = fields.Char(
        string='MercadoPago Client ID',
        help='Client ID for MercadoPago Point API'
    )
    mp_point_client_secret = fields.Char(
        string='MercadoPago Client Secret',
        help='Client Secret for MercadoPago Point API'
    )
    mp_point_sandbox_mode = fields.Boolean(
        string='Sandbox Mode',
        default=True,
        help='Use MercadoPago sandbox environment for testing'
    )

    @api.model
    def get_mp_point_base_url(self):
        """Get the base URL for MercadoPago API based on sandbox mode"""
        if self.mp_point_sandbox_mode:
            return 'https://api.mercadopago.com'
        else:
            return 'https://api.mercadopago.com'
