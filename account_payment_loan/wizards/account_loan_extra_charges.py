from odoo import Command, _, api, fields, models


class accountLoanExtraCharges(models.TransientModel):
    _name = "account.loan.extra.charges"
    _description = "Account Loan extra charges"

    partner_id = fields.Many2one("res.partner")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id")
    label = fields.Char(required=True, default=lambda x: _("Extra Charges"))
    available_loan_move_ids = fields.Many2many(
        comodel_name="account.move", string="Loans", compute="_compute_available_loan_move_ids"
    )
    loan_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Loan",
        required=False,
        # domain=[('id', 'in', available_loan_move_id)]
    )

    extra_charges = fields.Monetary(required=True)

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

    def action_add_extra_charges(self):
        loan_account_id = self.company_id.loan_journal_id.default_account_id
        extra_charges_account_id = self.company_id.account_loan_extra_charges
        if self.loan_move_id:
            base_loan_move_ids = self.loan_move_id.ids
        else:
            base_loan_move_ids = self.available_loan_move_ids.filtered(lambda x: not x.loan_move_ids).ids

        extra_charges_move_data = {
            "partner_id": self.partner_id.id,
            "journal_id": self.company_id.loan_journal_id.id,
            "loan_move_ids": [Command.set(base_loan_move_ids)],
            "line_ids": [
                Command.create(
                    {
                        "account_id": extra_charges_account_id.id,
                        "credit": self.extra_charges,
                        "name": self.label,
                        "currency_id": self.currency_id.id,
                    }
                ),
                Command.create(
                    {
                        "account_id": loan_account_id.id,
                        "debit": self.extra_charges,
                        "name": self.label,
                        "currency_id": self.currency_id.id,
                    }
                ),
            ],
        }
        extra_charges_move = self.env["account.move"].create(extra_charges_move_data)
        extra_charges_move.action_post()
