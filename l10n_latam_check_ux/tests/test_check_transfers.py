from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError
from odoo.tests.common import tagged


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nLatamCheckUxTransfers(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        cls.ar = ar = cls.env.ref("base.ar")

        cls.company = cls.company_data["company"]
        cls.company_bank_journal = cls.company_data["default_journal_bank"] or cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")], limit=1
        )
        cls.company_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "sale")], limit=1
        )
        third_party_checks_journals = cls.env["account.journal"].search(
            [
                ("company_id", "=", cls.company.id),
                ("inbound_payment_method_line_ids.code", "=", "in_third_party_checks"),
                ("inbound_payment_method_line_ids.code", "=", "new_third_party_checks"),
                (
                    "outbound_payment_method_line_ids.code",
                    "in",
                    ("out_third_party_checks", "return_third_party_checks"),
                ),
            ]
        )
        if len(third_party_checks_journals) < 2:
            inbound_account_id = cls.inbound_payment_method_line.payment_account_id.id
            outbound_account_id = cls.outbound_payment_method_line.payment_account_id.id

            def create_check_journal(name, code):
                return cls.env["account.journal"].create(
                    {
                        "name": name,
                        "code": code,
                        "type": "cash",
                        "company_id": cls.company.id,
                        "inbound_payment_method_line_ids": [
                            Command.create(
                                {
                                    "payment_method_id": cls.env.ref(
                                        "l10n_latam_check.account_payment_method_new_third_party_checks"
                                    ).id,
                                    "name": "Receive Third Party Checks",
                                    "payment_account_id": inbound_account_id,
                                }
                            ),
                            Command.create(
                                {
                                    "payment_method_id": cls.env.ref(
                                        "l10n_latam_check.account_payment_method_in_third_party_checks"
                                    ).id,
                                    "name": "Receive Existing Third Party Checks",
                                    "payment_account_id": inbound_account_id,
                                }
                            ),
                        ],
                        "outbound_payment_method_line_ids": [
                            Command.create(
                                {
                                    "payment_method_id": cls.env.ref(
                                        "l10n_latam_check.account_payment_method_out_third_party_checks"
                                    ).id,
                                    "name": "Deliver Third Party Checks",
                                    "payment_account_id": outbound_account_id,
                                }
                            )
                        ],
                    }
                )

            if len(third_party_checks_journals) == 0:
                third_party_checks_journals |= create_check_journal("Third Party Checks", "TPC")
                third_party_checks_journals |= create_check_journal("Rejected Third Party Checks", "RTC")
            else:
                third_party_checks_journals |= create_check_journal("Rejected Third Party Checks", "RTC")

        cls.third_party_check_journal = third_party_checks_journals[:1]
        cls.rejected_check_journal = third_party_checks_journals[1:2]

        cls.assertTrue(cls.company_bank_journal.ids, "A bank journal is required to run this test")
        cls.assertTrue(
            cls.third_party_check_journal.ids,
            "Third party check journal was not created so we can run the tests",
        )
        cls.assertTrue(
            cls.rejected_check_journal.ids,
            "Rejected check journal was not created so we can run the tests",
        )

        outbound_method_commands = []
        if not cls.company_bank_journal.outbound_payment_method_line_ids.filtered(
            lambda method: method.code == "own_checks"
        ):
            outbound_method_commands.append(
                Command.create(
                    {
                        "payment_method_id": cls.env.ref("l10n_latam_check.account_payment_method_own_checks").id,
                        "name": "Own Checks",
                        "payment_account_id": cls.outbound_payment_method_line.payment_account_id.id,
                    }
                )
            )
        if not cls.company_bank_journal.outbound_payment_method_line_ids.filtered(
            lambda method: method.code == "out_third_party_checks"
        ):
            outbound_method_commands.append(
                Command.create(
                    {
                        "payment_method_id": cls.env.ref(
                            "l10n_latam_check.account_payment_method_out_third_party_checks"
                        ).id,
                        "name": "Rejected Check",
                        "payment_account_id": cls.outbound_payment_method_line.payment_account_id.id,
                    }
                )
            )
        if outbound_method_commands:
            cls.company_bank_journal.write({"outbound_payment_method_line_ids": outbound_method_commands})

        if "use_payment_pro" in cls.company._fields:
            cls.company.use_payment_pro = True
        cls.eur_currency = cls.env["res.currency"].with_context(active_test=False).search([("name", "=", "EUR")])
        cls.eur_currency.active = True
        cls.partner_ri = cls.env["res.partner"].create(dict(name="RI Partner", vat="34278580484", country_id=ar.id))

    def _create_third_party_check(self, journal, check_number):
        payment = self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "payment_type": "inbound",
                "journal_id": journal.id,
                "l10n_latam_new_check_ids": [
                    Command.create(
                        {
                            "name": check_number,
                            "payment_date": fields.Date.add(fields.Date.today(), months=1),
                            "amount": 100.0,
                        }
                    )
                ],
                "payment_method_line_id": journal._get_available_payment_method_lines("inbound")
                .filtered(lambda x: x.code == "new_third_party_checks")[:1]
                .id,
            }
        )
        payment.action_post()
        return payment.l10n_latam_new_check_ids

    def test_deposit_third_party_check_to_bank(self):
        check = self._create_third_party_check(self.third_party_check_journal, "UX-DEP-0001")
        bank_journal = self.company_bank_journal

        self.env["l10n_latam.payment.mass.transfer"].with_context(
            active_model="l10n_latam.check",
            active_ids=check.ids,
        ).create(
            {
                "destination_journal_id": bank_journal.id,
            }
        )._create_payments()

        self.assertEqual(check.current_journal_id, bank_journal)

    def test_bank_rejection_receives_in_rejected_journal(self):
        check = self._create_third_party_check(self.third_party_check_journal, "UX-REJ-0001")
        bank_journal = self.company_bank_journal

        self.env["l10n_latam.payment.mass.transfer"].with_context(
            active_model="l10n_latam.check",
            active_ids=check.ids,
        ).create(
            {
                "destination_journal_id": bank_journal.id,
            }
        )._create_payments()

        self.env["l10n_latam.payment.mass.transfer"].with_context(
            active_model="l10n_latam.check",
            active_ids=check.ids,
        ).create(
            {
                "destination_journal_id": self.rejected_check_journal.id,
            }
        )._create_payments()

        last_operation = check._get_last_operation()
        self.assertEqual(check.current_journal_id, self.rejected_check_journal)
        self.assertEqual(last_operation.payment_type, "inbound")
        self.assertEqual(last_operation.payment_method_line_id.code, "in_third_party_checks")

    def test_internal_transfer_own_checks_bank_to_cash(self):
        bank_journal = self.company_bank_journal
        cash_journal = self.env["account.journal"].search(
            [
                ("company_id", "=", bank_journal.company_id.id),
                ("type", "=", "cash"),
            ],
            limit=1,
        )
        self.assertTrue(cash_journal, "A cash journal is required to run this test")

        own_checks_method = bank_journal._get_available_payment_method_lines("outbound").filtered(
            lambda x: x.code == "own_checks"
        )[:1]
        self.assertTrue(own_checks_method, "Bank journal must have own_checks payment method")

        payment = self.env["account.payment"].create(
            {
                "partner_id": self.partner_ri.id,
                "payment_type": "outbound",
                "journal_id": bank_journal.id,
                "destination_journal_id": cash_journal.id,
                "is_internal_transfer": True,
                "payment_method_line_id": own_checks_method.id,
                "l10n_latam_new_check_ids": [
                    Command.create(
                        {
                            "payment_date": fields.Date.add(fields.Date.today(), months=1),
                            "amount": 250.0,
                        }
                    )
                ],
            }
        )
        payment.action_post()

        self.assertEqual(payment.payment_method_line_id.code, "own_checks")
        self.assertTrue(payment.paired_internal_transfer_payment_id)
        self.assertEqual(payment.paired_internal_transfer_payment_id.journal_id, cash_journal)

    def test_inbound_internal_transfer_rejects_checks_from_other_current_journal(self):
        check_on_hand = self._create_third_party_check(self.third_party_check_journal, "UX-MIX-0001")
        check_rejected = self._create_third_party_check(self.rejected_check_journal, "UX-MIX-0002")

        payment_method_in = self.rejected_check_journal._get_available_payment_method_lines("inbound").filtered(
            lambda x: x.code == "in_third_party_checks"
        )[:1]

        with self.assertRaisesRegex(ValidationError, "All selected checks must belong to the source journal"):
            self.env["account.payment"].create(
                {
                    "partner_id": self.partner_ri.id,
                    "payment_type": "inbound",
                    "is_internal_transfer": True,
                    "journal_id": self.rejected_check_journal.id,
                    "destination_journal_id": self.third_party_check_journal.id,
                    "payment_method_line_id": payment_method_in.id,
                    "l10n_latam_move_check_ids": [Command.set((check_on_hand | check_rejected).ids)],
                    "amount": 200.0,
                }
            )
