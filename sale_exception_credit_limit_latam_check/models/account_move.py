from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _build_credit_warning_message(self, record, current_amount=0.0, exclude_current=False, exclude_amount=0.0):
        """``sale_exception_credit_limit`` builds the total from ``credit_with_confirmed_orders``, which
        already carries the checks on hand: tell ``l10n_latam_check_ux`` not to add them again, and
        only add the line that explains them."""
        message = super(AccountMove, self.with_context(checks_in_credit=True))._build_credit_warning_message(
            record,
            current_amount=current_amount,
            exclude_current=exclude_current,
            exclude_amount=exclude_amount,
        )
        partner = record.partner_id.commercial_partner_id.sudo()
        if not partner.use_partner_credit_limit:
            return message
        checks_amount = partner._get_on_hand_checks_credit(record.company_id)
        return self._add_checks_credit_warning_line(message, checks_amount, record.company_id)
