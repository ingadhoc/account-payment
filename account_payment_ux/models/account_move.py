from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _has_to_be_paid(self):
        # Unlike core, a pending transaction of any provider blocks, bank transfers (custom) included
        pending_transactions = self.transaction_ids.filtered(lambda tx: tx.state == "pending")
        return not pending_transactions and super()._has_to_be_paid()
