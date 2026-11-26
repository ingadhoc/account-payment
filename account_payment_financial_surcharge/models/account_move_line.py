from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _check_reconciliation(self):
        for line in self:
            if not line.full_reconcile_id and (line.matched_debit_ids or line.matched_credit_ids):
                self = self - line
        super(AccountMoveLine, self)._check_reconciliation()
