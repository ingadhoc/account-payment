from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _must_check_constrains_date_sequence(self):
        # OVERRIDES sequence.mixin
        self.ensure_one()
        if self.receiptbook_id:
            return False
        return super()._must_check_constrains_date_sequence()
