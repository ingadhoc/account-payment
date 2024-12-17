from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    use_payment_pro = fields.Boolean(
        related='company_id.use_payment_pro',
        readonly=False,
    )

    group_pay_now_customer_invoices = fields.Boolean(
        'Allow pay now on customer invoices?',
        implied_group='account_payment_pro.group_pay_now_customer_invoices',
    )
    group_pay_now_vendor_invoices = fields.Boolean(
        'Allow pay now on vendor invoices?',
        help='Allow users to choose a payment journal on invoices so that '
        'invoice is automatically paid after invoice validation. A payment '
        'will be created using choosen journal',
        implied_group='account_payment_pro.group_pay_now_vendor_invoices',
    )
