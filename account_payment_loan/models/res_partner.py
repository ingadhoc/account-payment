from odoo import _, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_loan_debt_report(self):
        self.ensure_one()

        view_id = self.env.ref("account_payment_loan.view_account_loan_debt_report_form").id
        view = {
            "name": _("Loan debit report"),
            "view_mode": "form",
            "view_id": view_id,
            "view_type": "form",
            "res_model": "account.loan.debt.report",
            "res_id": False,
            "type": "ir.actions.act_window",
            "target": "new",
            "context": {"default_partner_id": self.id},
        }
        return view

    def action_add_extra_charges(self, ctx=None):
        self.ensure_one()

        view_id = self.env.ref("account_payment_loan.view_account_loan_extra_charges_form").id
        view = {
            "name": _("Loan Extra Charges"),
            "view_mode": "form",
            "view_id": view_id,
            "view_type": "form",
            "res_model": "account.loan.extra.charges",
            "res_id": False,
            "type": "ir.actions.act_window",
            "target": "new",
            "context": {"default_partner_id": self.id},
        }
        return view
