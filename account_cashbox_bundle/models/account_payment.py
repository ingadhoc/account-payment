from odoo import api, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    @api.depends_context("uid")
    @api.depends("partner_id", "journal_id", "is_main_payment")
    def _compute_requiere_account_cashbox_session(self):
        super()._compute_requiere_account_cashbox_session()
        for rec in self:
            if rec.is_main_payment:
                rec.requiere_account_cashbox_session = False
