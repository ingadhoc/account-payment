from odoo import models


class HrExpenseSheetRegisterPaymentWizard(models.TransientModel):

    _inherit = "hr.expense.sheet.register.payment.wizard"

    def expense_post_payment(self):
        """ Update context in order to identify when a account.payment is
        created from an expense.
        """
        return super(
            HrExpenseSheetRegisterPaymentWizard,
            self.with_context(create_from_expense=True)
        ).expense_post_payment()
