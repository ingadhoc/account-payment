from odoo import _, api, fields, models


class l10nLatamAccountPaymentCheck(models.Model):
    _inherit = "l10n_latam.check"

    _unique = models.UniqueIndex("(name, payment_method_line_id) WHERE issue_state IS NOT NULL")

    name = fields.Char(tracking=True)
    issuer_vat = fields.Char(tracking=True)
    payment_date = fields.Date(tracking=True)
    bank_id = fields.Many2one(tracking=True)

    check_add_debit_button = fields.Boolean(related="original_journal_id.check_add_debit_button", readonly=True)
    can_reject = fields.Boolean(
        compute="_compute_can_reject",
    )
    date = fields.Date(related="payment_id.date")
    memo = fields.Char(related="payment_id.memo")
    company_id = fields.Many2one(
        compute="_compute_company_id", store=True, compute_sudo=True, comodel_name="res.company"
    )
    payment_state = fields.Selection(
        related="payment_id.state",
        readonly=True,
    )
    operation_ids = fields.Many2many(check_company=False)
    outstanding_line_id = fields.Many2one(check_company=False)
    user_can_write = fields.Boolean(
        compute="_compute_user_can_write",
    )

    def _compute_user_can_write(self):
        for rec in self:
            rec.user_can_write = rec.env.user.has_group("account.group_account_user")

    @api.depends("operation_ids.state", "payment_id.state")
    def _compute_company_id(self):
        for rec in self:
            last_operation = rec._get_last_operation() or rec.payment_id
            rec.company_id = last_operation.company_id

    def button_open_check_operations(self):
        action = super(l10nLatamAccountPaymentCheck, self.sudo()).button_open_check_operations()
        self.ensure_one()
        operations = self.operation_ids.sorted(lambda r: r.l10n_latam_move_check_ids_operation_date, reverse=True)
        # A check can travel between companies of the same hierarchy (branches), so we keep every
        # operation of the tree instead of only the ones of the company the check currently is in.
        operations = (operations + self.payment_id).filtered(
            lambda x: x.state not in ["draft", "canceled"] and x.company_id.root_id == self.company_id.root_id
        )
        action = {
            "name": _("Check Operations"),
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "views": [
                (self.env.ref("l10n_latam_check.view_account_third_party_check_operations_tree").id, "list"),
                (False, "form"),
            ],
            "context": {"create": False},
            "domain": [("id", "in", operations.ids)],
        }
        return action

    def _get_last_operation(self):
        super()._get_last_operation()
        self.ensure_one()
        return (
            (self.payment_id + self.operation_ids)
            .filtered(lambda x: x.state not in ["draft", "canceled"] and x.l10n_latam_move_check_ids_operation_date)
            .sorted(key=lambda payment: payment.l10n_latam_move_check_ids_operation_date)[-1:]
        )

    @api.depends("payment_method_line_id.code", "payment_id.partner_id")
    def _compute_bank_id(self):
        payment_method_change = self._origin.payment_method_line_id != self.payment_method_line_id
        partner_id_change = self._origin.payment_id.partner_id != self.payment_id.partner_id
        if payment_method_change or partner_id_change:
            super()._compute_bank_id()

    @api.depends("payment_method_line_id.code", "payment_id.partner_id")
    def _compute_issuer_vat(self):
        payment_method_change = self._origin.payment_method_line_id != self.payment_method_line_id
        partner_id_change = self._origin.payment_id.partner_id != self.payment_id.partner_id
        if payment_method_change or partner_id_change:
            super()._compute_issuer_vat()

    def _compute_issue_state(self):
        super()._compute_issue_state()
        for rec in self.filtered(lambda r: r.payment_method_code == "own_checks"):
            account = rec.outstanding_line_id.account_id
            if account and not account.reconcile:
                rec.issue_state = "debited"

    @api.depends(
        "payment_method_line_id",
        "payment_id.state",
        "operation_ids.state",
        "operation_ids.payment_method_line_id",
        "current_journal_id",
        "original_journal_id",
    )
    def _compute_can_reject(self):
        for rec in self:
            if rec.payment_method_code != "new_third_party_checks" or rec.payment_id.state in ("draft", "cancel"):
                rec.can_reject = False
                continue

            # Already returned to customer (rejection already processed).
            # We include both return_third_party_checks and out_third_party_checks because
            # some journals might not have the specific "return" method configured.
            if any(
                op.state == "posted"
                and op.payment_type == "outbound"
                and op.partner_type == "customer"
                and op.payment_method_code in ("return_third_party_checks", "out_third_party_checks")
                for op in rec.operation_ids
            ):
                rec.can_reject = False
                continue

            last_op = rec._get_last_operation()
            if not last_op:
                rec.can_reject = False
                continue

            # Case A: endorsed to a vendor (last outbound op with out_third_party_checks)
            endorsed = last_op.payment_method_code == "out_third_party_checks"
            # Case B: deposited/transferred to another journal (check is in a different journal than original)
            deposited = rec.current_journal_id != rec.original_journal_id

            rec.can_reject = endorsed or deposited
