from odoo import _, api, models
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    @api.constrains("currency_id")
    def _currency_in_bundle_journal(self):
        if self.filtered(
            lambda x: x.currency_id
            and "payment_bundle"
            in (x.inbound_payment_method_line_ids + x.outbound_payment_method_line_ids).mapped("code")
        ):
            raise ValidationError(
                _("You cannot assign a currency to journals that use the payment bundle payment method.")
            )

    @api.model_create_multi
    def create(self, vals_list):
        journals = super().create(vals_list)
        if bundle_journals := journals.filtered(
            lambda x: any(line.payment_method_id.code == "payment_bundle" for line in x.inbound_payment_method_line_ids)
            or any(line.payment_method_id.code == "payment_bundle" for line in x.outbound_payment_method_line_ids)
        ):
            for journal in bundle_journals:
                start_code = "6.0.0.00.001"
                journal.default_account_id.code = (
                    self.env["account.account"].with_company(journal.company_id)._search_new_account_code(start_code)
                )
        return journals

    def write(self, vals):
        res = super().write(vals)
        if "inbound_payment_method_line_ids" in vals or "outbound_payment_method_line_ids" in vals:
            self.env.registry.clear_cache()
        return res
