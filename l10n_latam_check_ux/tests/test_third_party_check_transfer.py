from odoo import Command
from odoo.tests.common import TransactionCase


class TestThirdPartyCheckTransfer(TransactionCase):
    """Test to validate the 'Split Payment' functionality when transferring third-party checks."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Obtain the company
        cls.company = cls.env.company

        # Use the company's currency
        cls.currency = cls.company.currency_id

        # Search for outstanding account (transitional account)
        cls.outstanding_account = cls.env["account.account"].search(
            [("account_type", "=", "asset_current"), ("reconcile", "=", True)], limit=1
        )
        if not cls.outstanding_account:
            # If there's no account with reconcile=True, search for any asset_current
            cls.outstanding_account = cls.env["account.account"].search(
                [("account_type", "=", "asset_current")], limit=1
            )

        # Create Checks Journal (Source)
        cls.journal_checks = cls.env["account.journal"].create(
            {
                "name": "Third Party Checks (Test)",
                "code": "TCHK",
                "type": "bank",
            }
        )

        # Create Bank Journal (Destination)
        cls.journal_bank = cls.env["account.journal"].create(
            {
                "name": "Bank (Test)",
                "code": "TBNK",
                "type": "bank",
            }
        )

        # Configure payment methods for third-party checks
        cls._setup_payment_methods()

        # Create partner for the checks
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Partner",
            }
        )

        # Create the three third-party checks
        cls.check_1 = cls._create_third_party_check(cls.journal_checks, "0000134", 1000.00, "2026-03-13")
        cls.check_2 = cls._create_third_party_check(cls.journal_checks, "00004567", 2000.00, "2026-04-12")
        cls.check_3 = cls._create_third_party_check(cls.journal_checks, "00007890", 3000.00, "2026-05-11")

    @classmethod
    def _setup_payment_methods(cls):
        """Configure payment methods for third-party checks."""
        # Search or create payment methods for third-party checks
        payment_method_in = cls.env["account.payment.method"].search(
            [("code", "=", "new_third_party_checks"), ("payment_type", "=", "inbound")], limit=1
        )
        if not payment_method_in:
            payment_method_in = cls.env["account.payment.method"].create(
                {
                    "name": "Third Party Checks",
                    "code": "new_third_party_checks",
                    "payment_type": "inbound",
                }
            )

        payment_method_out = cls.env["account.payment.method"].search(
            [("code", "=", "out_third_party_checks"), ("payment_type", "=", "outbound")], limit=1
        )
        if not payment_method_out:
            payment_method_out = cls.env["account.payment.method"].create(
                {
                    "name": "Out Third Party Checks",
                    "code": "out_third_party_checks",
                    "payment_type": "outbound",
                }
            )

        # Configure payment method lines in the journals
        cls.env["account.payment.method.line"].create(
            {
                "payment_method_id": payment_method_in.id,
                "journal_id": cls.journal_checks.id,
                "payment_account_id": cls.outstanding_account.id,  # Configure the outstanding account
            }
        )

        cls.env["account.payment.method.line"].create(
            {
                "payment_method_id": payment_method_out.id,
                "journal_id": cls.journal_checks.id,
                "payment_account_id": cls.outstanding_account.id,  # Configure the outstanding account
            }
        )

        cls.env["account.payment.method.line"].create(
            {
                "payment_method_id": payment_method_in.id,
                "journal_id": cls.journal_bank.id,
                "payment_account_id": cls.outstanding_account.id,  # Configure the outstanding account
            }
        )

    @classmethod
    def _create_third_party_check(cls, journal, check_number, amount, payment_date):
        """Create a third-party check and its associated payment."""
        # Get the payment method for third-party checks (inbound)
        payment_method_line = journal.inbound_payment_method_line_ids.filtered(
            lambda x: x.code == "new_third_party_checks"
        )

        if not payment_method_line:
            raise ValueError(f"Payment method 'new_third_party_checks' not found in journal {journal.name}")

        # Create the payment containing the check
        payment = cls.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_id": cls.partner.id,
                "amount": amount,
                "journal_id": journal.id,
                "payment_method_line_id": payment_method_line.id,
                "date": payment_date,
                "l10n_latam_new_check_ids": [
                    Command.create(
                        {
                            "name": check_number,
                            "amount": amount,
                            "payment_date": payment_date,
                            "currency_id": cls.currency.id,
                        }
                    )
                ],
            }
        )

        # Post the payment so the check is in 'holding' state
        payment.action_post()

        # Get the created check - after posting, new checks are moved to move_check_ids
        # or can be searched by payment ID
        check = cls.env["l10n_latam.check"].search([("payment_id", "=", payment.id)], limit=1)
        if not check:
            raise ValueError(f"Could not create check for payment {payment.id}")

        return check

    def test_transfer_third_party_checks_with_split_payment(self):
        """
        Test: Transfer multiple third-party checks with 'Split Payment' option enabled.
        It should create an individual payment for each check.
        """
        # 1. Group the three checks
        checks_to_transfer = self.check_1 | self.check_2 | self.check_3

        # Verify that the checks exist
        self.assertEqual(len(self.check_1), 1, "Check 1 must exist")
        self.assertEqual(len(self.check_2), 1, "Check 2 must exist")
        self.assertEqual(len(self.check_3), 1, "Check 3 must exist")

        # 2. Create the transfer wizard
        wizard = self.env["l10n_latam.payment.mass.transfer"].create(
            {
                "journal_id": self.journal_checks.id,
                "destination_journal_id": self.journal_bank.id,
                "check_ids": [Command.set(checks_to_transfer.ids)],
                "split_payment": True,
                "payment_date": "2026-06-13",  # Future date to avoid validation errors
            }
        )

        # 3. Execute the transfer
        wizard.action_create_payments()

        # 4. Validate individual payment creation
        created_payments = self.env["account.payment"].search(
            [
                ("journal_id", "=", self.journal_checks.id),
                ("destination_journal_id", "=", self.journal_bank.id),
                ("is_internal_transfer", "=", True),
            ]
        )

        self.assertEqual(len(created_payments), 3, "3 separate transfer payments must be created")

        # 5. Validate data and relationships of each payment
        # Sort payments by amount to identify them
        payment_1 = created_payments.filtered(lambda p: p.amount == 1000.00)
        payment_2 = created_payments.filtered(lambda p: p.amount == 2000.00)
        payment_3 = created_payments.filtered(lambda p: p.amount == 3000.00)

        # Validate that each payment was found
        self.assertEqual(len(payment_1), 1, "There must be exactly one payment of 1000.00")
        self.assertEqual(len(payment_2), 1, "There must be exactly one payment of 2000.00")
        self.assertEqual(len(payment_3), 1, "There must be exactly one payment of 3000.00")

        # Validations for payment 1 (from check_1)
        self.assertEqual(payment_1.amount, 1000.00, "Payment 1 amount must be 1000.00")
        self.assertEqual(payment_1.journal_id, self.journal_checks, "Payment 1 journal must be the checks journal")
        self.assertEqual(payment_1.destination_journal_id, self.journal_bank, "Payment 1 destination must be the bank")
        self.assertIn(self.check_1, payment_1.l10n_latam_move_check_ids, "Payment 1 must contain check_1")

        # Validations for payment 2 (from check_2)
        self.assertEqual(payment_2.amount, 2000.00, "Payment 2 amount must be 2000.00")
        self.assertEqual(payment_2.journal_id, self.journal_checks, "Payment 2 journal must be the checks journal")
        self.assertEqual(payment_2.destination_journal_id, self.journal_bank, "Payment 2 destination must be the bank")
        self.assertIn(self.check_2, payment_2.l10n_latam_move_check_ids, "Payment 2 must contain check_2")

        # Validations for payment 3 (from check_3)
        self.assertEqual(payment_3.amount, 3000.00, "Payment 3 amount must be 3000.00")
        self.assertEqual(payment_3.journal_id, self.journal_checks, "Payment 3 journal must be the checks journal")
        self.assertEqual(payment_3.destination_journal_id, self.journal_bank, "Payment 3 destination must be the bank")
        self.assertIn(self.check_3, payment_3.l10n_latam_move_check_ids, "Payment 3 must contain check_3")
