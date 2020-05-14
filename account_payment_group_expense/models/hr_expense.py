from odoo import models


class HrExpense(models.Model):

    _inherit = "hr.expense"

    def action_move_create(self):
        """ Update context in order to identify when a account.payment is
        created from an expense.
        """
        return super(
            HrExpense, self.with_context(create_from_expense=True)
        ).action_move_create()
