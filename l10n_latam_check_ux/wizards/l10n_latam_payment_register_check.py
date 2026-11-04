from odoo import api, fields, models


class L10nLatamPaymentRegisterCheck(models.TransientModel):
    _inherit = "l10n_latam.payment.register.check"

    bank_id = fields.Many2one("res.bank", compute="_compute_bank_id", store=True, readonly=False)

    @api.depends("payment_register_id.payment_method_line_id.code", "payment_register_id.partner_id")
    def _compute_bank_id(self):
        new_third_party_checks = self.filtered(
            lambda x: x.payment_register_id.payment_method_line_id.code == "new_third_party_checks"
        )
        for rec in new_third_party_checks:
            rec.bank_id = rec.payment_register_id.partner_id.bank_ids[:1].bank_id
        (self - new_third_party_checks).bank_id = False

    @api.depends("bank_id")
    def _compute_bank_account_id(self):
        super()._compute_bank_account_id()
        for rec in self.filtered(
            lambda x: x.bank_id and x.payment_register_id.payment_method_line_id.code == "new_third_party_checks"
        ):
            partner_accounts = rec.payment_register_id.partner_id.bank_ids
            rec.bank_account_id = partner_accounts.filtered(lambda a: a.bank_id == rec.bank_id)[:1]
