from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    use_payment_pro = fields.Boolean(compute="_compute_use_payment_pro", store=True, readonly=False)

    payment_receipt_full_ref = fields.Boolean(
        "Show full reference on imputed vouchers",
        help="On the payment receipt / payment order report, show the full reference of the imputed "
        "vouchers instead of the shortened version that cuts long references with '[...]'.",
    )

    @api.depends("partner_id.country_id")
    def _compute_use_payment_pro(self):
        ar_companies = self.filtered(lambda x: x.partner_id.country_id.code == "AR")
        ar_companies.use_payment_pro = True
        (self - ar_companies).use_payment_pro = False
