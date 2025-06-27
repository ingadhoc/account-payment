from odoo import Command, _, api, fields, models


class accountLoanDebtDeport(models.TransientModel):
    _name = "account.loan.debt.report"
    _description = "Account Loan debt report"

    partner_id = fields.Many2one("res.partner")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id")
    amount = fields.Monetary()
    available_loan_move_ids = fields.Many2many(
        comodel_name="account.move", string="Loans", compute="_compute_available_loan_move_ids"
    )
    loan_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Loan",
        required=False,
        # domain=[('id', 'in', available_loan_move_id)]
    )
    financial_surchage = fields.Monetary(compute="_compute_financial_surchage")
    move_line_ids = fields.Many2many(
        comodel_name="account.move.line",
        string="Loan Lines",
    )
    amount_to_pay = fields.Monetary(compute="_compute_amount_to_pay")

    @api.onchange("loan_move_id")
    def _onchange_loan_move_id(self):
        if self.loan_move_id:
            self.move_line_ids = [Command.clear()]

    @api.depends("partner_id")
    def _compute_available_loan_move_ids(self):
        for rec in self:
            loan_account_id = self.env.company.loan_journal_id.default_account_id
            loan_line_ids = self.env["account.move.line"].search(
                [
                    ("company_id", "=", self.env.company.id),
                    ("account_id", "=", loan_account_id.id),
                    ("partner_id", "=", self.partner_id.id),
                    ("parent_state", "=", "posted"),
                    ("amount_residual", ">", 0),
                ]
            )
            rec.available_loan_move_ids = [(6, 0, loan_line_ids.mapped("move_id").ids)]

    @api.depends("move_line_ids")
    def _compute_financial_surchage(self):
        for rec in self:
            rec.financial_surchage = rec.move_line_ids.mapped("move_id")._get_total_debit() or 0.0

    @api.depends("financial_surchage", "move_line_ids")
    def _compute_amount_to_pay(self):
        for rec in self:
            rec.amount_to_pay = rec.financial_surchage + sum(rec.move_line_ids.mapped("amount_residual"))

    def action_payment_items(self):
        return self.move_line_ids.action_payment_items_register_payment()

    def action_set_financial_surcharge(self):
        if self.loan_move_id:
            self.loan_move_id.create_financial_surchage_move()
        else:
            self.available_loan_move_ids.filtered(lambda x: not x.loan_move_ids).create_financial_surchage_move()

    def action_refinancial_loan(self):
        context = {
            "refinancial_loan_move_ids": [self.loan_move_id.id]
            if self.loan_move_id
            else self.available_loan_move_ids.ids,
        }
        return {
            "name": _("Refinancial Loan"),
            "res_model": "account.loan.register",
            "view_mode": "form",
            "views": [[False, "form"]],
            "context": context,
            "target": "new",
            "type": "ir.actions.act_window",
        }
