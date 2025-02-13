from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    use_receiptbook = fields.Boolean(compute="_compute_use_receiptbook", store=True, readonly=False)

    @api.constrains("use_receiptbook", "use_payment_pro")
    def _check_use_receiptbook(self):
        for record in self:
            if record.use_receiptbook and not record.use_payment_pro:
                raise ValidationError("You can only enable 'Use Receipt Book' if 'Use Payment Pro' is also enabled.")

    @api.depends("partner_id.country_id", "use_payment_pro")
    def _compute_use_receiptbook(self):
        ar_companies = self.filtered(lambda x: x.use_payment_pro and x.partner_id.country_id.code == "AR")
        ar_companies.use_receiptbook = True
        (self - ar_companies).use_receiptbook = False
