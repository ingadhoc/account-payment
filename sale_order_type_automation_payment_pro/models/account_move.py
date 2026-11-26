# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _prepare_dict_account_payment(self, invoice, payment_journal):
        res = super()._prepare_dict_account_payment(invoice, payment_journal)
        # With account_payment_pro installed, creating the payment with only partner_id
        # triggers _compute_to_pay_move_lines -> _add_all(), which loads the partner's
        # whole open debt and ends up reconciling the old invoice instead of the one from
        # the flow. Passing to_pay_move_line_ids explicitly in create makes the ORM skip
        # the compute for that field (same pattern as account.move.pay_now()), so the
        # payment stays scoped to the invoice that triggered the automation.
        res["to_pay_move_line_ids"] = [Command.set(invoice.open_move_line_ids.ids)]
        return res
