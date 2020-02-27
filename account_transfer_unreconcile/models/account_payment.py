# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_draft(self):
        for rec in self:
            if rec.payment_type == 'transfer':
                transfer_account = rec.company_id.transfer_account_id
                rec.move_line_ids.filtered(
                    lambda x: x.account_id == transfer_account
                ).remove_move_reconcile()
        return super().action_draft()
