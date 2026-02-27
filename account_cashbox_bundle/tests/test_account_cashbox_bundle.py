from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestAccountCashboxBundle(common.TransactionCase):
    """Tests for account_cashbox_bundle module integration"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Use Responsable Inscripto company (same as demo data)
        cls.company = cls.env.ref("base.company_ri")

        # Load demo data dynamically
        chart = cls.env["account.chart.template"].with_company(cls.company)
        chart._install_account_cashbox_bundle_demo([cls.company])

        # Reference demo data using chart.ref() with company context
        cls.demo_partner = chart.ref("demo_partner_cashbox")
        cls.demo_user_cashbox = chart.ref("demo_user_requires_cashbox")

        # Find existing cash and bank journals instead of creating demo ones
        cls.demo_journal_cash = cls.env["account.journal"].search(
            [("type", "=", "cash"), ("company_id", "=", cls.company.id)], limit=1
        )
        cls.demo_journal_bank = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.company.id)], limit=1
        )

        # Ensure we found the required journals for testing
        if not cls.demo_journal_cash:
            raise ValueError(
                "No cash journal found for company %s. Cannot run cashbox bundle tests." % cls.company.name
            )
        if not cls.demo_journal_bank:
            raise ValueError(
                "No bank journal found for company %s. Cannot run cashbox bundle tests." % cls.company.name
            )

        # Use the bundle journal created by l10n_ar_payment_bundle
        cls.demo_journal_bundle = chart.ref("payment_bundle_journal")
        cls.demo_cashbox = chart.ref("demo_cashbox_main")

    def test_bundle_journal_not_in_cashbox_domain(self):
        """
        Test Case 1: Bundle journals should not be selectable in cashbox configuration
        Validates that journals with payment_bundle method are excluded from journal_ids domain
        """
        # Get the domain from the field definition
        journal_field = self.env["account.cashbox"]._fields["journal_ids"]
        domain = journal_field.domain

        # Apply domain to search journals
        if callable(domain):
            domain = domain(self.env["account.cashbox"])

        available_journals = self.env["account.journal"].search(domain)

        # Verify bundle journal is NOT in available journals
        self.assertNotIn(
            self.demo_journal_bundle,
            available_journals,
            "Bundle journal should not be available in cashbox configuration",
        )

        # Verify regular cash/bank journals ARE available
        self.assertIn(
            self.demo_journal_cash,
            available_journals,
            "Regular cash journal should be available in cashbox configuration",
        )
        self.assertIn(
            self.demo_journal_bank,
            available_journals,
            "Regular bank journal should be available in cashbox configuration",
        )

    def test_main_payment_no_cashbox_session_required(self):
        """
        Test Case 2 & 3: Main payment (bundle) should not require cashbox session
        Child payments should require cashbox session if user requires it
        """
        # Create main payment (bundle payment)
        main_payment = (
            self.env["account.payment"]
            .with_user(self.demo_user_cashbox)
            .create(
                {
                    "payment_type": "outbound",
                    "partner_id": self.demo_partner.id,
                    "amount": 0,
                    "journal_id": self.demo_journal_bundle.id,
                    "payment_method_line_id": self.env["account.payment.method.line"]
                    .search(
                        [
                            ("journal_id", "=", self.demo_journal_bundle.id),
                            ("payment_method_id.code", "=", "payment_bundle"),
                        ],
                        limit=1,
                    )
                    .id,
                }
            )
        )

        # Verify it's marked as main payment
        self.assertTrue(main_payment.is_main_payment, "Payment with bundle method should be marked as main payment")

        # Verify main payment does NOT require cashbox session
        self.assertFalse(
            main_payment.requiere_account_cashbox_session, "Main payment (bundle) should not require cashbox session"
        )

        # Create a child payment linked to main payment
        child_payment = (
            self.env["account.payment"]
            .with_user(self.demo_user_cashbox)
            .create(
                {
                    "payment_type": "outbound",
                    "partner_id": self.demo_partner.id,
                    "amount": 100.0,
                    "journal_id": self.demo_journal_cash.id,
                    "main_payment_id": main_payment.id,
                }
            )
        )

        # Verify child payment is NOT a main payment
        self.assertFalse(child_payment.is_main_payment, "Child payment should not be marked as main payment")

        # Verify child payment DOES require cashbox session (user has requiere_account_cashbox_session = True)
        self.assertTrue(
            child_payment.requiere_account_cashbox_session,
            "Child payment should require cashbox session when user requires it",
        )

    def test_bundle_only_withholdings_no_session_required(self):
        """
        Test Case 3: Bundle payment with only withholdings (is_main_payment) doesn't require session
        This is the same as test_main_payment_no_cashbox_session_required because withholdings
        are only added to main payments, not to child payments
        """
        # Create main payment (which could have only withholdings)
        main_payment_withholdings = (
            self.env["account.payment"]
            .with_user(self.demo_user_cashbox)
            .create(
                {
                    "payment_type": "outbound",
                    "partner_id": self.demo_partner.id,
                    "amount": 0,  # Main payment amount is always 0
                    "journal_id": self.demo_journal_bundle.id,
                    "payment_method_line_id": self.env["account.payment.method.line"]
                    .search(
                        [
                            ("journal_id", "=", self.demo_journal_bundle.id),
                            ("payment_method_id.code", "=", "payment_bundle"),
                        ],
                        limit=1,
                    )
                    .id,
                }
            )
        )

        # Verify it doesn't require cashbox session (even if it only has withholdings)
        self.assertFalse(
            main_payment_withholdings.requiere_account_cashbox_session,
            "Bundle payment with only withholdings should not require cashbox session",
        )

    def test_user_without_session_requirement(self):
        """
        Additional test: Verify that without requiere_account_cashbox_session,
        both main and child payments don't require session
        """
        # Create a regular user without session requirement
        regular_user = self.env["res.users"].create(
            {
                "name": "Regular User",
                "login": "regular_user",
                "email": "regular@test.com",
                "requiere_account_cashbox_session": False,
                "company_id": self.company.id,
                "company_ids": [(4, self.company.id)],
            }
        )

        # Create payments with this user
        main_payment = (
            self.env["account.payment"]
            .with_user(regular_user)
            .create(
                {
                    "payment_type": "outbound",
                    "partner_id": self.demo_partner.id,
                    "amount": 0,
                    "journal_id": self.demo_journal_bundle.id,
                    "company_id": self.company.id,
                    "payment_method_line_id": self.env["account.payment.method.line"]
                    .search(
                        [
                            ("journal_id", "=", self.demo_journal_bundle.id),
                            ("payment_method_id.code", "=", "payment_bundle"),
                        ],
                        limit=1,
                    )
                    .id,
                }
            )
        )

        child_payment = (
            self.env["account.payment"]
            .with_user(regular_user)
            .create(
                {
                    "payment_type": "outbound",
                    "partner_id": self.demo_partner.id,
                    "amount": 100.0,
                    "journal_id": self.demo_journal_cash.id,
                    "main_payment_id": main_payment.id,
                    "company_id": self.company.id,
                }
            )
        )

        # Neither should require session
        self.assertFalse(
            main_payment.requiere_account_cashbox_session,
            "Main payment should not require session when user doesn't require it",
        )
        self.assertFalse(
            child_payment.requiere_account_cashbox_session,
            "Child payment should not require session when user doesn't require it",
        )
