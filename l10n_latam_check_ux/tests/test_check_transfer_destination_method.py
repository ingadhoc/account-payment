# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestCheckTransferDestinationMethod(AccountTestInvoicingCommon):
    """Depositing checks lets the user pick the payment method line of the destination journal.

    The destination journal can hold two inbound lines with different outstanding accounts, one
    for checks pending to be credited and another one for transfers. Until now the deposit always
    landed on the third party checks line, so the other account could not be reached.
    """

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

        # the destination journal has both lines: checks pending and transfers pending
        cls.destination_journal = cls.env["account.journal"].create(
            {
                "name": "Destination Cash",
                "code": "DSTDM",
                "type": "cash",
                "company_id": company.id,
                "inbound_payment_method_line_ids": [
                    Command.create(
                        {
                            "payment_method_id": cls.env.ref(
                                "l10n_latam_check.account_payment_method_in_third_party_checks"
                            ).id,
                            "payment_account_id": outstanding_account.id,
                        }
                    )
                ],
            }
        )
        cls.checks_destination_line = cls.destination_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "in_third_party_checks"
        )
        # passing inbound_payment_method_line_ids on create skips the manual line odoo would add,
        # so the second outstanding account gets its own line here
        cls.transfers_destination_line = cls.env["account.payment.method.line"].create(
            {
                "name": "Transfers Pending",
                "payment_method_id": cls.env.ref("account.account_payment_method_manual_in").id,
                "payment_account_id": cls.transfers_outstanding_account.id,
                "journal_id": cls.destination_journal.id,
            }
        )

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

    def _transfer_wizard(self, checks, destination_line=None, split_payment=False):
        wizard = (
            self.env["l10n_latam.payment.mass.transfer"]
            .with_context(active_model="l10n_latam.check", active_ids=checks.ids)
            .create(
                {
                    "payment_date": fields.Date.today(),
                    "destination_journal_id": self.destination_journal.id,
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
        wizard = self._transfer_wizard(self._receive_check())

        self.assertEqual(wizard.destination_payment_method_line_id, self.checks_destination_line)

    def test_available_lines_are_the_inbound_ones_of_the_destination_journal(self):
        wizard = self._transfer_wizard(self._receive_check())

        self.assertIn(self.transfers_destination_line, wizard.available_destination_payment_method_line_ids)
        self.assertIn(self.checks_destination_line, wizard.available_destination_payment_method_line_ids)
        self.assertNotIn(self.new_check_line, wizard.available_destination_payment_method_line_ids)

    def test_grouped_deposit_uses_the_chosen_line(self):
        """The case that could not be reached: destination journal with the checks line present."""
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
        wizard = self._transfer_wizard(checks)

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
