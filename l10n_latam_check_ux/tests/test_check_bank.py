from odoo import Command, fields
from odoo.tests import Form, tagged

from .common import LatamCheckCommon


@tagged("post_install", "-at_install")
class TestCheckBank(LatamCheckCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_a = cls.env["res.bank"].create({"name": "Test Bank A"})
        cls.bank_b = cls.env["res.bank"].create({"name": "Test Bank B"})
        cls.bank_c = cls.env["res.bank"].create({"name": "Test Bank C"})
        cls.account_a = cls.env["res.partner.bank"].create(
            {"partner_id": cls.partner.id, "account_number": "0050001234567890123456", "bank_id": cls.bank_a.id}
        )

    def _create_payment(self, check_vals):
        return self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "journal_id": self.third_party_journal.id,
                "payment_method_line_id": self.new_third_party_line.id,
                "l10n_latam_new_check_ids": [
                    Command.create(
                        {
                            "name": "00000001",
                            "issuer_vat": self.partner.vat,
                            "payment_date": fields.Date.add(self.today, months=1),
                            "amount": 1,
                            **check_vals,
                        }
                    )
                ],
            }
        )

    def test_bank_proposed_from_partner_account(self):
        with Form(self.env["account.payment"].with_context(default_payment_type="inbound")) as payment_form:
            payment_form.partner_id = self.partner
            payment_form.journal_id = self.third_party_journal
            payment_form.payment_method_line_id = self.new_third_party_line
            with payment_form.l10n_latam_new_check_ids.new() as check_form:
                check_form.name = "00000001"
                check_form.payment_date = fields.Date.add(self.today, months=1)
                check_form.amount = 1
                self.assertEqual(check_form.bank_id, self.bank_a)
        check = payment_form.save().l10n_latam_new_check_ids
        self.assertEqual(check.bank_id, self.bank_a)
        self.assertEqual(check.bank_account_id, self.account_a)

    def test_endorsed_check_keeps_bank_without_account(self):
        check = self._create_payment({"bank_id": self.bank_b.id}).l10n_latam_new_check_ids
        self.assertEqual(check.bank_id, self.bank_b)
        self.assertFalse(check.bank_account_id)

    def test_duplicated_check_warning_compares_bank(self):
        # Endorsed checks: the partner has no account in these banks, so none of them has a bank account
        self._create_payment({"bank_id": self.bank_b.id}).action_post()
        same_bank = self._create_payment({"bank_id": self.bank_b.id})
        other_bank = self._create_payment({"bank_id": self.bank_c.id})
        self.assertFalse(same_bank.l10n_latam_new_check_ids.bank_account_id)
        self.assertEqual((same_bank.l10n_latam_check_warning_msg or "").count("same number, issuer and bank"), 1)
        self.assertFalse(other_bank.l10n_latam_check_warning_msg)
