from odoo import api, models, fields


class ResCompany(models.Model):
    _inherit = "res.company"

    use_payment_pro = fields.Boolean(compute='_compute_use_payment_pro', store=True, readonly=False)

    @api.depends('partner_id.country_id.code')
    def _compute_use_payment_pro(self):
        ar_companies = self.filtered(lambda x: x.partner_id.country_id.code == 'AR')
        ar_companies.use_payment_pro = True
        (self - ar_companies).use_payment_pro = False
