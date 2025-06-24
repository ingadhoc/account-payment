from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    def _init_payments(self, to_process, edit_mode=False):
        for rec in to_process:
            if self.env["res.company"].browse(rec["create_vals"]["company_id"]).use_payment_pro:
                rec["create_vals"]["name"] = "/"
        return super()._init_payments(to_process, edit_mode=edit_mode)
