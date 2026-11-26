# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged


class CheckTransferDestinationCommon(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.company_data["company"]
        outstanding_account = cls.inbound_payment_method_line.payment_account_id
        cls.transfers_outstanding_account = cls.copy_account(outstanding_account)

        cls.check_journal = cls.env["account.journal"].create(
            {
                "name": "Third Party Checks",
                "code": "TPCDM",
                "type": "cash",
                "company_id": company.id,
                "inbound_payment_method_line_ids": [
                    Command.create(
                        {
                            "payment_method_id": cls.env.ref(
                                "l10n_latam_check.account_payment_method_new_third_party_checks"
                            ).id,
                            "payment_account_id": outstanding_account.id,
                        }
                    )
                ],
            }
        )
        cls.new_check_line = cls.check_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "new_third_party_checks"
        )
        cls.env["account.payment.method.line"].create(
            {
                "payment_method_id": cls.env.ref("l10n_latam_check.account_payment_method_out_third_party_checks").id,
                "payment_account_id": outstanding_account.id,
                "journal_id": cls.check_journal.id,
            }
        )

        # a checks journal that also accepts new checks and has a manual line: only the checks line can
        # receive a transfer, otherwise the checks would not stay in portfolio
        cls.destination_journal = cls.env["account.journal"].create(
            {
                "name": "Destination Checks",
                "code": "DSTDM",
                "type": "cash",
                "company_id": company.id,
                "inbound_payment_method_line_ids": [
                    Command.create(
                        {
                            "payment_method_id": cls.env.ref(
                                "l10n_latam_check.account_payment_method_new_third_party_checks"
                            ).id,
                            "payment_account_id": outstanding_account.id,
                            "sequence": 5,
                        }
                    ),
                    Command.create(
                        {
                            "payment_method_id": cls.env.ref(
                                "l10n_latam_check.account_payment_method_in_third_party_checks"
                            ).id,
                            "payment_account_id": outstanding_account.id,
                            "sequence": 20,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Manual",
                            "payment_method_id": cls.env.ref("account.account_payment_method_manual_in").id,
                            "payment_account_id": outstanding_account.id,
                            "sequence": 10,
                        }
                    ),
                ],
            }
        )
        cls.destination_new_check_line = cls.destination_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "new_third_party_checks"
        )
        cls.checks_destination_line = cls.destination_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "in_third_party_checks"
        )
        cls.destination_manual_line = cls.destination_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "manual"
        )

        # the bank has two inbound lines: checks pending and transfers pending. Passing
        # inbound_payment_method_line_ids on create skips the manual line odoo would add
        cls.bank_journal = cls.env["account.journal"].create(
            {
                "name": "Destination Bank",
                "code": "DSTBK",
                "type": "bank",
                "company_id": company.id,
                "inbound_payment_method_line_ids": [
                    Command.create(
                        {
                            "name": "Checks Pending",
                            "payment_method_id": cls.env.ref("account.account_payment_method_manual_in").id,
                            "sequence": 10,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Transfers Pending",
                            "payment_method_id": cls.env.ref("account.account_payment_method_manual_in").id,
                            "sequence": 20,
                        }
                    ),
                ],
            }
        )
        cls.checks_pending_line, cls.transfers_destination_line = (
            cls.bank_journal.inbound_payment_method_line_ids.sorted("sequence")
        )
        # some modules overwrite the outstanding accounts of a new bank journal (saas_client_account)
        cls.checks_pending_line.payment_account_id = outstanding_account
        cls.transfers_destination_line.payment_account_id = cls.transfers_outstanding_account

    @classmethod
    def _receive_check(cls, check_number="00000001"):
        payment = cls.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": cls.partner_a.id,
                "journal_id": cls.check_journal.id,
                "payment_method_line_id": cls.new_check_line.id,
                "l10n_latam_new_check_ids": [
                    Command.create(
                        {
                            "name": check_number,
                            "payment_date": fields.Date.add(fields.Date.today(), months=1),
                            "amount": 100.0,
                        }
                    )
                ],
            }
        )
        payment.action_post()
        return payment.l10n_latam_new_check_ids


@tagged("post_install", "-at_install")
class TestCheckTransferDestinationMethod(CheckTransferDestinationCommon):
    """Depositing checks lets the user pick the payment method line of the destination journal.

    A bank can hold two inbound lines with different outstanding accounts, one for checks pending
    to be credited and another one for transfers. On a checks journal only the checks line keeps
    the checks in portfolio, so it is the only one offered.
    """

    def _transfer_wizard(self, checks, destination_line=None, split_payment=False, destination_journal=None):
        wizard = (
            self.env["l10n_latam.payment.mass.transfer"]
            .with_context(active_model="l10n_latam.check", active_ids=checks.ids)
            .create(
                {
                    "payment_date": fields.Date.today(),
                    "destination_journal_id": (destination_journal or self.bank_journal).id,
                    "split_payment": split_payment,
                }
            )
        )
        if destination_line:
            wizard.destination_payment_method_line_id = destination_line
        return wizard

    def _inbound_payment_of(self, outbound_payment):
        return outbound_payment.paired_internal_transfer_payment_id

    def test_default_is_the_third_party_checks_line(self):
        """The default has to keep depositing on the checks line, as before the field existed."""
        wizard = self._transfer_wizard(self._receive_check(), destination_journal=self.destination_journal)

        self.assertEqual(wizard.destination_payment_method_line_id, self.checks_destination_line)

    def test_checks_journal_only_offers_the_checks_line(self):
        """Neither the new checks line nor a manual one: the checks would not stay in portfolio."""
        wizard = self._transfer_wizard(self._receive_check(), destination_journal=self.destination_journal)

        self.assertEqual(wizard.available_destination_payment_method_line_ids, self.checks_destination_line)

    def test_checks_journal_rejects_another_line(self):
        wizard = self._transfer_wizard(self._receive_check(), destination_journal=self.destination_journal)

        with self.assertRaises(ValidationError):
            wizard.destination_payment_method_line_id = self.destination_manual_line

    def test_bank_offers_its_inbound_lines(self):
        wizard = self._transfer_wizard(self._receive_check())

        self.assertEqual(
            wizard.available_destination_payment_method_line_ids,
            self.checks_pending_line | self.transfers_destination_line,
        )
        self.assertEqual(wizard.destination_payment_method_line_id, self.checks_pending_line)

    def test_grouped_deposit_uses_the_chosen_line(self):
        """The case that could not be reached: a line other than the first one of the bank."""
        checks = self._receive_check()
        wizard = self._transfer_wizard(checks, destination_line=self.transfers_destination_line)

        outbound_payment = wizard._create_payments()

        inbound_payment = self._inbound_payment_of(outbound_payment)
        self.assertEqual(inbound_payment.payment_method_line_id, self.transfers_destination_line)
        self.assertIn(
            self.transfers_outstanding_account,
            inbound_payment.move_id.line_ids.mapped("account_id"),
            "The deposit has to hit the outstanding account of the chosen line.",
        )

    def test_grouped_deposit_keeps_the_checks_linked_to_the_payment(self):
        """Posting with a line that is not for checks must not unlink them."""
        checks = self._receive_check()
        wizard = self._transfer_wizard(checks, destination_line=self.transfers_destination_line)

        outbound_payment = wizard._create_payments()

        self.assertEqual(self._inbound_payment_of(outbound_payment).l10n_latam_move_check_ids, checks)

    def test_grouped_deposit_without_choice_keeps_the_previous_behaviour(self):
        checks = self._receive_check()
        wizard = self._transfer_wizard(checks, destination_journal=self.destination_journal)

        outbound_payment = wizard._create_payments()

        self.assertEqual(
            self._inbound_payment_of(outbound_payment).payment_method_line_id,
            self.checks_destination_line,
        )

    def test_grouped_deposit_creates_only_two_payments(self):
        """check_deposit_transfer has to keep action_post from adding a third payment."""
        checks = self._receive_check()
        wizard = self._transfer_wizard(checks, destination_line=self.transfers_destination_line)

        outbound_payment = wizard._create_payments()

        self.assertEqual(len(outbound_payment), 1)
        self.assertEqual(
            self._inbound_payment_of(outbound_payment).paired_internal_transfer_payment_id,
            outbound_payment,
        )

    def test_split_deposit_uses_the_chosen_line(self):
        checks = self._receive_check() | self._receive_check(check_number="00000002")
        wizard = self._transfer_wizard(checks, destination_line=self.transfers_destination_line, split_payment=True)

        outbound_payments = wizard._create_payments()

        self.assertEqual(len(outbound_payments), 2)
        for outbound_payment in outbound_payments:
            inbound_payment = self._inbound_payment_of(outbound_payment)
            self.assertEqual(inbound_payment.payment_method_line_id, self.transfers_destination_line)
            self.assertTrue(
                inbound_payment.l10n_latam_move_check_ids,
                "The checks must stay linked when the chosen line is not for checks.",
            )


@tagged("post_install", "-at_install")
class TestCheckInternalTransferDestinationMethod(CheckTransferDestinationCommon):
    """A check transfer made from the payment form, towards a checks journal that also accepts new checks.

    The new checks line comes first by sequence. The paired payment must not take it: a transfer brings
    no new checks, so the paired payment ended up with amount 0 and the check in the wrong journal.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.company_data["company"]
        outstanding_account = cls.inbound_payment_method_line.payment_account_id
        cls.deposit_journal = cls.env["account.journal"].create(
            {
                "name": "Checks to Deposit",
                "code": "TPCDP",
                "type": "cash",
                "company_id": company.id,
                "inbound_payment_method_line_ids": [
                    Command.create(
                        {
                            "payment_method_id": cls.env.ref(
                                "l10n_latam_check.account_payment_method_new_third_party_checks"
                            ).id,
                            "payment_account_id": outstanding_account.id,
                            "sequence": 10,
                        }
                    ),
                    Command.create(
                        {
                            "payment_method_id": cls.env.ref(
                                "l10n_latam_check.account_payment_method_in_third_party_checks"
                            ).id,
                            "payment_account_id": outstanding_account.id,
                            "sequence": 11,
                        }
                    ),
                ],
            }
        )
        cls.deposit_new_check_line = cls.deposit_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "new_third_party_checks"
        )
        cls.deposit_in_check_line = cls.deposit_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "in_third_party_checks"
        )
        cls.out_check_line = cls.check_journal.outbound_payment_method_line_ids.filtered(
            lambda line: line.code == "out_third_party_checks"
        )

    def _internal_transfer(self, checks, destination_journal):
        return self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "is_internal_transfer": True,
                "journal_id": self.check_journal.id,
                "payment_method_line_id": self.out_check_line.id,
                "destination_journal_id": destination_journal.id,
                "l10n_latam_move_check_ids": [Command.set(checks.ids)],
            }
        )

    def test_new_checks_line_is_not_available_as_destination(self):
        transfer = self._internal_transfer(self._receive_check(), self.deposit_journal)

        self.assertNotIn(self.deposit_new_check_line, transfer.available_destination_payment_method_line_ids)
        self.assertIn(self.deposit_in_check_line, transfer.available_destination_payment_method_line_ids)

    def test_default_is_the_third_party_checks_line(self):
        transfer = self._internal_transfer(self._receive_check(), self.deposit_journal)

        self.assertEqual(transfer.destination_payment_method_line_id, self.deposit_in_check_line)

    def test_default_prefers_checks_line_over_sequence(self):
        """The manual line comes before the checks line by sequence."""
        transfer = self._internal_transfer(self._receive_check(), self.destination_journal)

        self.assertEqual(transfer.available_destination_payment_method_line_ids, self.checks_destination_line)
        self.assertEqual(transfer.destination_payment_method_line_id, self.checks_destination_line)

    def test_checks_journal_rejects_a_manual_line(self):
        transfer = self._internal_transfer(self._receive_check(), self.destination_journal)

        with self.assertRaises(ValidationError):
            transfer.destination_payment_method_line_id = self.destination_manual_line

    def test_explicit_choice_is_kept(self):
        transfer = self._internal_transfer(self._receive_check(), self.bank_journal)
        transfer.destination_payment_method_line_id = self.transfers_destination_line

        transfer.action_post()

        self.assertEqual(
            transfer.paired_internal_transfer_payment_id.payment_method_line_id, self.transfers_destination_line
        )

    def test_paired_payment_keeps_amount_and_checks(self):
        checks = self._receive_check()
        transfer = self._internal_transfer(checks, self.deposit_journal)

        transfer.action_post()

        paired_payment = transfer.paired_internal_transfer_payment_id
        self.assertEqual(paired_payment.journal_id, self.deposit_journal)
        self.assertEqual(paired_payment.payment_method_line_id, self.deposit_in_check_line)
        self.assertEqual(paired_payment.amount, 100.0)
        self.assertEqual(paired_payment.l10n_latam_move_check_ids, checks)
        self.assertEqual(checks.current_journal_id, self.deposit_journal)
