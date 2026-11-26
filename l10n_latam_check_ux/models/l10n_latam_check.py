from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

THIRD_PARTY_CHECK_STATES = [
    ("on_hand", "In Portfolio"),
    ("deposited", "Deposited"),
    ("endorsed", "Endorsed"),
    ("rejected", "Rejected"),
    ("returned", "Returned"),
]
OWN_CHECK_STATES = [
    ("handed", "Issued"),
    ("debited", "Debited"),
    ("voided", "Voided"),
]

# Which check states each list action accepts (the matrix of task 80427). An action is offered for a
# selection only when it applies to every selected check.
CHECK_ACTION_STATES = {
    "deposit": ("on_hand",),
    "transfer": ("on_hand",),
    "endorse": ("on_hand",),
    "return": ("on_hand", "rejected"),
    # rejecting a check in portfolio comes with task 78297
    "reject": ("deposited", "endorsed"),
    "debit": ("handed",),
    "void": ("handed",),
}


class l10nLatamAccountPaymentCheck(models.Model):
    _inherit = "l10n_latam.check"

    _unique = models.UniqueIndex("(name, payment_method_line_id) WHERE issue_state IS NOT NULL")

    name = fields.Char(tracking=True)
    issuer_vat = fields.Char(tracking=True)
    payment_date = fields.Date(tracking=True)
    bank_account_id = fields.Many2one(tracking=True)
    # Odoo 20 replaced the bank of the check with a bank account of the partner, which an endorsed
    # check usually does not have: the issuer bank is chosen from the catalog again, as in 19.0
    bank_id = fields.Many2one(
        "res.bank", compute="_compute_bank_id", store=True, readonly=False, tracking=True, index="btree_not_null"
    )

    check_add_debit_button = fields.Boolean(related="original_journal_id.check_add_debit_button", readonly=True)
    can_reject = fields.Boolean(
        compute="_compute_can_reject",
    )
    date = fields.Date(related="payment_id.date")
    memo = fields.Char(related="payment_id.memo")
    # related=False: otherwise the core related field wins and _compute_company_id never triggers
    company_id = fields.Many2one(
        related=False, compute="_compute_company_id", store=True, compute_sudo=True, comodel_name="res.company"
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
    check_state = fields.Selection(
        selection=THIRD_PARTY_CHECK_STATES + OWN_CHECK_STATES,
        compute="_compute_check_state",
        store=True,
        index=True,
        help="Where the check stands. Third party checks: in portfolio, deposited, endorsed, rejected or returned. "
        "Own checks: issued, debited or voided.",
    )
    operations_summary = fields.Text(
        string="Operations",
        compute="_compute_operations_summary",
        help="Payments of the third party check, one per line, oldest first.",
    )

    @api.depends(
        "payment_method_line_id.code",
        "issue_state",
        "current_journal_id.type",
        "current_journal_id.l10n_latam_rejected_checks",
        "payment_id.state",
        "operation_ids.state",
        "operation_ids.payment_type",
        "operation_ids.partner_type",
        "operation_ids.l10n_latam_move_check_ids_operation_date",
    )
    def _compute_check_state(self):
        for rec in self:
            rec.check_state = rec._get_check_state()

    def _get_check_state(self):
        self.ensure_one()
        code = self.payment_method_line_id.code
        if code == "own_checks":
            return self.issue_state
        if code != "new_third_party_checks":
            return False
        last_operation = self._get_last_operation()
        if not last_operation:
            return False
        if last_operation.payment_type == "outbound":
            # an internal transfer is always followed by its inbound pair, so it is never the last operation
            if last_operation.is_internal_transfer:
                return False
            # same criteria as _compute_can_reject: some journals have no specific "return" method
            if last_operation.partner_type == "customer":
                return "returned"
            return "endorsed"
        journal = self.current_journal_id
        # the rejected checks journal can be of type cash, so it goes before "in portfolio"
        if journal.l10n_latam_rejected_checks:
            return "rejected"
        if journal.type == "bank":
            return "deposited"
        if journal.type == "cash":
            return "on_hand"
        return False

    @api.depends(
        "payment_method_line_id.code",
        "payment_id.state",
        "payment_id.name",
        "operation_ids.state",
        "operation_ids.name",
        "operation_ids.l10n_latam_move_check_ids_operation_date",
    )
    def _compute_operations_summary(self):
        third_party_checks = self.filtered(lambda c: c.payment_method_line_id.code == "new_third_party_checks")
        (self - third_party_checks).operations_summary = False
        for rec in third_party_checks:
            # one payment per line, oldest first: Text fields keep line breaks in the list
            rec.operations_summary = "\n".join(rec._get_operations().mapped("name"))

    def _compute_user_can_write(self):
        for rec in self:
            rec.user_can_write = rec.env.user.has_group("account.group_account_user")

    # Both computes below resolve the last operation of the chain, and that order comes from the
    # operation date. The core depends only on the states, so fixing the date of an operation --a
    # migration script, an import, a manual correction-- reordered the chain but left these stored
    # fields with the old value, and the check kept showing in the portfolio after it was handed
    # over. Adding a depends does not recompute the existing records, so installing this does not
    # move checks that are fine today.
    @api.depends(
        "operation_ids.state",
        "payment_id.state",
    )
    def _compute_company_id(self):
        for rec in self:
            last_operation = rec._get_last_operation() or rec.payment_id
            rec.company_id = last_operation.company_id

    @api.depends(
        "operation_ids.state",
        "payment_id.state",
        "operation_ids.l10n_latam_move_check_ids_operation_date",
        "payment_id.l10n_latam_move_check_ids_operation_date",
    )
    def _compute_current_journal(self):
        super()._compute_current_journal()

    def button_open_check_operations(self):
        action = super(l10nLatamAccountPaymentCheck, self.sudo()).button_open_check_operations()
        self.ensure_one()
        # Filtering comes first: a draft has no operation date yet, and sorting it against the
        # confirmed ones compares None with a datetime.
        # A check can travel between companies of the same hierarchy (branches), so we keep every
        # operation of the tree instead of only the ones of the company the check currently is in.
        operations = (
            (self.operation_ids + self.payment_id)
            .filtered(
                lambda x: x.state not in ["draft", "canceled"] and x.company_id.root_id == self.company_id.root_id
            )
            .sorted(lambda r: r.l10n_latam_move_check_ids_operation_date, reverse=True)
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

    def _get_operations(self):
        self.ensure_one()
        # El desempate por id es necesario: sin el, dos operaciones con la misma fecha quedan en el
        # orden en que las devolvio el recordset, que no es estable ni significativo.
        return (
            (self.payment_id + self.operation_ids)
            .filtered(lambda x: x.state not in ["draft", "canceled"] and x.l10n_latam_move_check_ids_operation_date)
            .sorted(key=lambda payment: (payment.l10n_latam_move_check_ids_operation_date, payment._origin.id))
        )

    @api.depends("payment_method_line_id.code", "payment_id.partner_id")
    def _compute_bank_id(self):
        # Only a change of method or partner proposes the bank again, so the one chosen by hand is kept
        payment_method_change = self._origin.payment_method_line_id != self.payment_method_line_id
        partner_id_change = self._origin.payment_id.partner_id != self.payment_id.partner_id
        if not (payment_method_change or partner_id_change):
            return
        new_third_party_checks = self.filtered(lambda x: x.payment_method_line_id.code == "new_third_party_checks")
        for rec in new_third_party_checks:
            rec.bank_id = rec.partner_id.bank_ids[:1].bank_id
        (self - new_third_party_checks).bank_id = False

    @api.depends("payment_method_line_id.code", "payment_id.partner_id", "bank_id")
    def _compute_bank_account_id(self):
        payment_method_change = self._origin.payment_method_line_id != self.payment_method_line_id
        partner_id_change = self._origin.payment_id.partner_id != self.payment_id.partner_id
        if payment_method_change or partner_id_change:
            super()._compute_bank_account_id()
        for rec in self.filtered(lambda x: x.bank_id and x.payment_method_line_id.code == "new_third_party_checks"):
            rec.bank_account_id = rec.partner_id.bank_ids.filtered(lambda a: a.bank_id == rec.bank_id)[:1]

    @api.depends("payment_method_line_id.code", "payment_id.partner_id")
    def _compute_issuer_vat(self):
        payment_method_change = self._origin.payment_method_line_id != self.payment_method_line_id
        partner_id_change = self._origin.payment_id.partner_id != self.payment_id.partner_id
        if payment_method_change or partner_id_change:
            super()._compute_issuer_vat()

    @api.depends("outstanding_line_id.amount_residual")
    def _compute_issue_state(self):
        """Solo los cheques propios tienen estado de emisión (tarea 70884).

        Con una línea de liquidez por cheque los de terceros también tienen ``outstanding_line_id``,
        así que un core anterior a odoo/odoo@d85e16a les daría un estado y entrarían al índice único
        de arriba, donde el mismo número de dos libradores distintos es válido. Desde d85e16a base
        filtra igual; esto queda para las imágenes con un core anterior.

        El ``@api.depends`` no se puede sacar: el ORM lee las dependencias del método más derivado
        del MRO. Efecto colateral pinneado por los tests ``_today``: un cheque propio en borrador
        queda 'debited', porque su línea todavía no tiene residual.
        """
        super()._compute_issue_state()
        self.filtered(lambda r: r.payment_method_code != "own_checks").issue_state = False

        # si la cuenta no es conciliable no queda nada por debitar
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

    # ------------------------------------------------------------------
    # List actions: each one is offered only for the states of the matrix
    # ------------------------------------------------------------------
    def _get_check_action_label(self, action):
        return {
            "deposit": _("Deposit"),
            "transfer": _("Transfer"),
            "endorse": _("Endorse"),
            "return": _("Return to Customer"),
            "reject": _("Reject"),
            "debit": _("Debit"),
            "void": _("Void"),
        }[action]

    def _get_check_action_errors(self, action):
        """Return the reasons why ``action`` does not apply to these checks, one line per problem.

        An empty list means the action can run on the whole selection.
        """
        if not self:
            return [_("Select at least one check.")]
        state_labels = dict(self._fields["check_state"]._description_selection(self.env))
        allowed_states = CHECK_ACTION_STATES[action]
        errors = []
        for check in self:
            if check.check_state not in allowed_states:
                errors.append(
                    _(
                        "%(check)s is %(state)s; it must be %(allowed)s.",
                        check=check.display_name,
                        state=state_labels.get(check.check_state, _("without state")),
                        allowed=_(" or ").join(state_labels[state] for state in allowed_states),
                    )
                )
            elif action == "reject" and not check.can_reject:
                errors.append(_("%(check)s cannot be rejected.", check=check.display_name))
            elif action == "debit" and not check.check_add_debit_button:
                errors.append(
                    _(
                        "%(check)s: the journal %(journal)s does not allow debiting checks with a button.",
                        check=check.display_name,
                        journal=check.original_journal_id.display_name,
                    )
                )
        if errors:
            return errors
        if action in ("deposit", "transfer", "endorse", "return") and len(self.current_journal_id) > 1:
            errors.append(
                _(
                    "The checks are on different journals (%(journals)s); they are moved one journal at a time.",
                    journals=", ".join(self.current_journal_id.mapped("display_name")),
                )
            )
        if action == "return" and len(self.partner_id) > 1:
            errors.append(_("The checks belong to different customers; they are returned one customer at a time."))
        if action == "reject" and len(self.company_id) > 1:
            errors.append(_("All selected checks must belong to the same company."))
        if action == "void" and len(self) > 1:
            errors.append(_("Checks are voided one at a time."))
        return errors

    def _check_action_allowed(self, action):
        errors = self._get_check_action_errors(action)
        if errors:
            raise UserError(
                _(
                    "%(action)s cannot be applied to the selected checks:\n%(errors)s",
                    action=self._get_check_action_label(action),
                    errors="\n".join("- %s" % error for error in errors),
                )
            )

    def _get_check_wizard_action(self, xml_id, name=None, **context):
        action = self.env["ir.actions.act_window"]._for_xml_id(xml_id)
        action["context"] = {
            "active_model": self._name,
            "active_ids": self.ids,
            "active_id": self[:1].id,
            **context,
        }
        if name:
            action["name"] = name
        return action

    def action_check_deposit(self):
        self._check_action_allowed("deposit")
        return self._get_check_wizard_action(
            "l10n_latam_check.action_view_l10n_latam_payment_mass_transfer",
            name=_("Deposit Checks"),
            default_transfer_mode="deposit",
        )

    def action_check_transfer(self):
        self._check_action_allowed("transfer")
        return self._get_check_wizard_action(
            "l10n_latam_check.action_view_l10n_latam_payment_mass_transfer",
            name=_("Transfer Checks"),
            default_transfer_mode="transfer",
        )

    def action_check_reject(self):
        self._check_action_allowed("reject")
        return self._get_check_wizard_action("l10n_latam_check_ux.action_reject_check_wizard")

    def action_check_debit(self):
        self._check_action_allowed("debit")
        return self._get_check_wizard_action("l10n_latam_check_ux.action_debit_check_wizard", name=_("Debit Checks"))

    def action_check_void(self):
        self._check_action_allowed("void")
        self.action_void()
        return True

    def action_check_endorse(self):
        """Open a draft vendor payment with the checks already loaded.

        It is not posted from here: debts, withholdings and other payment methods are completed on the payment
        form, as when the payment is created by hand.
        """
        self._check_action_allowed("endorse")
        journal = self.current_journal_id
        method_line = journal._get_available_payment_method_lines("outbound").filtered(
            lambda x: x.code == "out_third_party_checks"
        )[:1]
        if not method_line:
            raise UserError(
                _(
                    "The journal %(journal)s has no outbound payment method of type 'Existing Third Party Checks'.",
                    journal=journal.display_name,
                )
            )
        return self._get_check_payment_form_action(
            _("Endorse Checks"), journal, method_line, partner_type="supplier", partner=False
        )

    def action_check_return(self):
        """Open a draft payment returning the checks to the customer that gave them."""
        self._check_action_allowed("return")
        journal = self.current_journal_id
        lines = journal._get_available_payment_method_lines("outbound")
        method_line = (
            lines.filtered(lambda x: x.code == "return_third_party_checks")[:1]
            or lines.filtered(lambda x: x.code == "out_third_party_checks")[:1]
        )
        if not method_line:
            raise UserError(
                _(
                    "The journal %(journal)s has no outbound payment method of type 'Return Third Party Checks' or "
                    "'Existing Third Party Checks'.",
                    journal=journal.display_name,
                )
            )
        return self._get_check_payment_form_action(
            _("Return Checks to Customer"), journal, method_line, partner_type="customer", partner=self.partner_id
        )

    def _get_check_payment_form_action(self, name, journal, method_line, partner_type, partner):
        context = {
            "default_payment_type": "outbound",
            "default_partner_type": partner_type,
            "default_journal_id": journal.id,
            "default_company_id": journal.company_id.id,
            "default_payment_method_line_id": method_line.id,
            "default_l10n_latam_move_check_ids": [fields.Command.set(self.ids)],
        }
        if partner:
            context["default_partner_id"] = partner.id
        return {
            "name": name,
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "views": [(False, "form")],
            "target": "current",
            "context": context,
        }

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @api.model
    def _get_dashboard_sections(self):
        return {
            "third_party": {
                "domain": [("payment_method_line_id.code", "=", "new_third_party_checks")],
                "states": [state for state, _label in THIRD_PARTY_CHECK_STATES],
                "due_state": "on_hand",
                "filters": {state: "check_state_%s" % state for state, _label in THIRD_PARTY_CHECK_STATES},
            },
            "own": {
                "domain": [("payment_method_line_id.code", "=", "own_checks")],
                "states": [state for state, _label in OWN_CHECK_STATES],
                "due_state": "handed",
                # the core filters of own checks, on issue_state, which check_state copies
                "filters": {"handed": "checks_handed", "debited": "checks_debited", "voided": "checks_voided"},
            },
        }

    @api.model
    def _get_dashboard_due_domain(self):
        today = fields.Date.context_today(self)
        return [("payment_date", ">=", today), ("payment_date", "<=", today + timedelta(days=7))]

    @api.model
    def get_check_dashboard_data(self, section_key):
        """Cards of the KPIs shown on top of a checks list: count and amount per state, for the active companies.

        Amounts are grouped by currency: checks in different currencies are never added up. Each card carries the
        names of the search filters that show its checks.
        """
        section = self._get_dashboard_sections()[section_key]
        state_labels = dict(self._fields["check_state"]._description_selection(self.env))
        base_domain = [("company_id", "in", self.env.companies.ids)] + section["domain"]
        filters = section["filters"]
        cards = {
            state: {
                "key": state,
                "label": state_labels[state],
                "count": 0,
                "amounts": [],
                "filters": [filters[state]],
            }
            for state in section["states"]
        }
        for state, currency, count, amount in self._read_group(
            base_domain + [("check_state", "in", section["states"])],
            ["check_state", "payment_id.currency_id"],
            ["__count", "amount:sum"],
        ):
            cards[state]["count"] += count
            cards[state]["amounts"].append({"currency_id": currency.id, "amount": amount})
        due = {
            "key": "due_week",
            "label": _("Due This Week"),
            "count": 0,
            "amounts": [],
            "filters": [filters[section["due_state"]], "due_week"],
        }
        for currency, count, amount in self._read_group(
            base_domain + [("check_state", "=", section["due_state"])] + self._get_dashboard_due_domain(),
            ["payment_id.currency_id"],
            ["__count", "amount:sum"],
        ):
            due["count"] += count
            due["amounts"].append({"currency_id": currency.id, "amount": amount})
        return list(cards.values()) + [due]
