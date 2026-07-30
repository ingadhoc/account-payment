##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import Command, fields
from odoo.tests import TransactionCase


class LatamCheckCommon(TransactionCase):
    """Self-contained check setup for the l10n_latam_check_ux suites.

    Builds its own journals, payment method lines and outstanding accounts on
    ``env.company`` with ``.create()``, so the suite does not depend on a
    localization being installed nor on demo data.

    The core ``l10n_latam_check`` tests cannot be reused: their common calls
    ``setup_other_company(country_id=base.ar)`` twice, and creating an extra
    Argentine company is rejected on OBA databases by
    ``saas_client_account._check_country_currency`` ("You cannot select a
    currency that is different from the country's currency"), so they error out
    at ``setUpClass``. Inheriting ``AccountTestInvoicingCommon`` on its own is
    fine - what breaks is the extra company.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        cls.company = cls.env.company
        cls.company_currency = cls.company.currency_id
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))

        cls.partner = cls.env["res.partner"].create({"name": "Check Test Partner", "vat": "30710158254"})
        cls.bank = cls.env["res.bank"].search([], limit=1) or cls.env["res.bank"].create({"name": "Test Bank"})

        # Accounts: one reconcilable outstanding account per check type + a
        # non-reconcilable one to exercise the ux issue_state override.
        cls.deferred_check_account = cls._create_account("TDEFCHK", "Test Deferred Checks", reconcile=True)
        cls.third_party_account = cls._create_account("TTPCHK", "Test Third Party Checks", reconcile=True)
        cls.manual_outstanding_account = cls._create_account("TOUTMAN", "Test Outstanding Manual", reconcile=True)
        cls.destination_account = cls._create_account(
            "TDEST", "Test Payable", account_type="liability_payable", reconcile=True
        )
        cls.receivable_account = cls._create_account(
            "TRECV", "Test Receivable", account_type="asset_receivable", reconcile=True
        )
        cls.expense_account = cls._create_account("TEXP", "Test Expense", account_type="expense")
        # internal transfers need it and it is not set on every database
        if not cls.company.transfer_account_id:
            cls.company.transfer_account_id = cls._create_account("TTRANSF", "Test Internal Transfer", reconcile=True)

        # payment_pro rewrites the liquidity/counterpart balances of every payment
        # when enabled, which would hide what these tests are about (the core +
        # l10n_latam_check_ux mechanism). Its own suite covers the combination.
        if "use_payment_pro" in cls.env["res.company"]._fields:
            cls.company.use_payment_pro = False

        cls.own_checks_method = cls.env.ref("l10n_latam_check.account_payment_method_own_checks")
        cls.new_third_party_method = cls.env.ref("l10n_latam_check.account_payment_method_new_third_party_checks")
        cls.in_third_party_method = cls.env.ref("l10n_latam_check.account_payment_method_in_third_party_checks")
        cls.out_third_party_method = cls.env.ref("l10n_latam_check.account_payment_method_out_third_party_checks")
        cls.return_third_party_method = cls.env.ref("l10n_latam_check.account_payment_method_return_third_party_checks")
        cls.manual_out_method = cls.env.ref("account.account_payment_method_manual_out")
        cls.manual_in_method = cls.env.ref("account.account_payment_method_manual_in")

        # Bank journal issuing own checks (+ manual method, needed by the debit wizard).
        cls.bank_journal = cls.env["account.journal"].create(
            {
                "name": "Test Checks Bank",
                "code": "TCHKB",
                "type": "bank",
                "company_id": cls.company.id,
                "check_add_debit_button": True,
            }
        )
        cls.own_checks_line = cls._add_method_line(
            cls.bank_journal, cls.own_checks_method, "Own Checks", cls.deferred_check_account
        )
        cls.manual_out_line = cls._add_method_line(
            cls.bank_journal, cls.manual_out_method, "Manual", cls.manual_outstanding_account
        )
        cls._add_method_line(cls.bank_journal, cls.manual_in_method, "Manual", cls.manual_outstanding_account)
        # needed to move a deposited check out of the bank journal (rejections)
        cls._add_method_line(
            cls.bank_journal, cls.return_third_party_method, "Return Third Party Checks", cls.third_party_account
        )

        # Two third party check journals (a regular one and the rejected one).
        cls.third_party_journal = cls._create_third_party_journal("Test Third Party Checks", "TTPC")
        cls.rejected_journal = cls._create_third_party_journal("Test Rejected Checks", "TRJC")
        cls.new_third_party_line = cls._get_method_line(cls.third_party_journal, "new_third_party_checks")
        cls.in_third_party_line = cls._get_method_line(cls.third_party_journal, "in_third_party_checks")
        cls.out_third_party_line = cls._get_method_line(cls.third_party_journal, "out_third_party_checks")

        # Foreign currency with a rate on the payment date and a *different* rate
        # 30 days later, so deferred checks (payment_date > date) can tell apart
        # a conversion done at the payment date from one done at the check date.
        cls.foreign_currency = cls._setup_foreign_currency()

    # ------------------------------------------------------------------
    # setup helpers
    # ------------------------------------------------------------------
    @classmethod
    def _create_account(cls, code, name, account_type="asset_current", reconcile=False):
        return cls.env["account.account"].create(
            {
                "name": name,
                "code": code,
                "account_type": account_type,
                "reconcile": reconcile,
                "company_ids": [Command.set(cls.company.ids)],
            }
        )

    @classmethod
    def _add_method_line(cls, journal, payment_method, name, account):
        field = (
            "inbound_payment_method_line_ids"
            if payment_method.payment_type == "inbound"
            else "outbound_payment_method_line_ids"
        )
        journal.write(
            {
                field: [
                    Command.create(
                        {"payment_method_id": payment_method.id, "name": name, "payment_account_id": account.id}
                    )
                ]
            }
        )
        return journal[field].filtered(lambda line: line.payment_method_id == payment_method)[-1]

    @classmethod
    def _create_third_party_journal(cls, name, code):
        journal = cls.env["account.journal"].create(
            {"name": name, "code": code, "type": "cash", "company_id": cls.company.id}
        )
        for method, label in (
            (cls.new_third_party_method, "New Third Party Checks"),
            (cls.in_third_party_method, "Existing Third Party Checks"),
            (cls.out_third_party_method, "Deliver Third Party Checks"),
        ):
            cls._add_method_line(journal, method, label, cls.third_party_account)
        return journal

    @classmethod
    def _get_method_line(cls, journal, code):
        lines = journal.inbound_payment_method_line_ids + journal.outbound_payment_method_line_ids
        return lines.filtered(lambda line: line.code == code)[:1]

    @classmethod
    def _setup_foreign_currency(cls):
        """Currency other than the company one, created instead of reused.

        Which currencies exist and which are active depends on the database (a
        ``search`` here silently returns nothing when the candidates are
        archived), and the rates have to be exactly these two: one today and a
        different one 30 days later, so a deferred check can tell apart a
        conversion made at the payment date from one made at the check date.
        """
        currency = cls.env["res.currency"].create(
            {
                "name": "TCK",
                "symbol": "T$",
                "rounding": 0.01,
            }
        )
        cls.env["res.currency.rate"].create(
            [
                {
                    "name": cls.today,
                    "currency_id": currency.id,
                    "company_id": cls.company.id,
                    "rate": 1 / 100.0,
                },
                {
                    "name": fields.Date.add(cls.today, days=30),
                    "currency_id": currency.id,
                    "company_id": cls.company.id,
                    "rate": 1 / 200.0,
                },
            ]
        )
        return currency

    # ------------------------------------------------------------------
    # payment factories
    # ------------------------------------------------------------------
    def _new_check_vals(self, amount, number=None, payment_date=None, issuer=False):
        vals = {"amount": amount, "payment_date": payment_date or self.today, "name": number}
        if issuer:
            vals.update({"issuer_vat": "30710158254", "bank_id": self.bank.id})
        return vals

    def _create_own_check_payment(
        self, amounts, numbers=None, currency=None, date=None, check_dates=None, method_line=None
    ):
        """Outbound payment issuing one own check per amount.

        ``method_line`` (and its journal) is set at create time on purpose: the
        unique index on the check covers ``payment_method_line_id``, so moving a
        payment to another checkbook afterwards would leave the check colliding
        with its siblings until the write lands.
        """
        numbers = numbers or [None] * len(amounts)
        check_dates = check_dates or [date or self.today] * len(amounts)
        method_line = method_line or self.own_checks_line
        return self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.partner.id,
                "journal_id": method_line.journal_id.id,
                "company_id": self.company.id,
                "date": date or self.today,
                "currency_id": (currency or self.company_currency).id,
                "payment_method_line_id": method_line.id,
                "l10n_latam_new_check_ids": [
                    Command.create(self._new_check_vals(amount, numbers[i], check_dates[i]))
                    for i, amount in enumerate(amounts)
                ],
            }
        )

    def _receive_third_party_checks(self, amounts, numbers=None, currency=None, date=None):
        """Inbound payment receiving new third party checks."""
        numbers = numbers or [None] * len(amounts)
        return self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "journal_id": self.third_party_journal.id,
                "company_id": self.company.id,
                "date": date or self.today,
                "currency_id": (currency or self.company_currency).id,
                "payment_method_line_id": self.new_third_party_line.id,
                "l10n_latam_new_check_ids": [
                    Command.create(self._new_check_vals(amount, numbers[i], issuer=True))
                    for i, amount in enumerate(amounts)
                ],
            }
        )

    def _deliver_third_party_checks(self, checks, date=None):
        """Outbound payment endorsing existing third party checks to a vendor."""
        return self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.partner.id,
                "journal_id": self.third_party_journal.id,
                "company_id": self.company.id,
                "date": date or self.today,
                "payment_method_line_id": self.out_third_party_line.id,
                "l10n_latam_move_check_ids": [Command.set(checks.ids)],
            }
        )

    def _create_debt_move(self, amount, account=None, date=None):
        """Posted journal entry with a payable/receivable line the payment can reconcile with."""
        account = account or self.destination_account
        counterpart = self.expense_account
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": date or self.today,
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": "debt",
                            "account_id": account.id,
                            "partner_id": self.partner.id,
                            "credit": amount,
                        }
                    ),
                    Command.create({"name": "debt cp", "account_id": counterpart.id, "debit": amount}),
                ],
            }
        )
        move.action_post()
        return move.line_ids.filtered(lambda line: line.account_id == account)

    # ------------------------------------------------------------------
    # assertion helpers
    # ------------------------------------------------------------------
    def _check_lines(self, payment):
        """Liquidity lines carrying a check (one per check with the new mechanism)."""
        return payment.move_id.line_ids.filtered("l10n_latam_check_ids").sorted("id")

    def _counterpart_lines(self, payment):
        return payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type in ("liability_payable", "asset_receivable")
        )

    def assert_move_balanced(self, move, msg=""):
        self.assertEqual(
            move.company_currency_id.round(sum(move.line_ids.mapped("balance"))),
            0.0,
            "Journal entry %s is not balanced. %s" % (move.name, msg),
        )

    def assert_check_lines_match(self, payment, msg=""):
        """Every check has its own liquidity line, on the outstanding account,
        holding its nominal amount, maturing on its own date, labelled with its
        number and reachable back from the check.

        Everything a check line must satisfy lives here on purpose: every suite
        calling this helper gets the full contract instead of each test
        re-asserting a slice of it.
        """
        checks = payment.l10n_latam_new_check_ids or payment.l10n_latam_move_check_ids
        lines = self._check_lines(payment)
        self.assertEqual(len(lines), len(checks), "One liquidity line per check expected. %s" % msg)
        for check in checks:
            line = lines.filtered(lambda x: check in x.l10n_latam_check_ids)
            self.assertEqual(len(line), 1, "Check %s must be linked to exactly one line" % check.name)
            self.assertEqual(
                abs(line.amount_currency),
                check.amount,
                "Line of check %s must hold the check nominal in the payment currency" % check.name,
            )
            self.assertEqual(
                line.date_maturity, check.payment_date, "Line of check %s must mature on the check date" % check.name
            )
            self.assertEqual(
                line.account_id,
                payment.outstanding_account_id,
                "Line of check %s must sit on the outstanding account" % check.name,
            )
            self.assertEqual(check.outstanding_line_id, line, "Check %s must point back to its own line" % check.name)
            if check.name:
                self.assertIn(check.name, line.name or "", "The line label must carry the check number")
