from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestLoanAccountSetup(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def test_loan_account_id_is_set(self):
        self.assertTrue(self.company.loan_account_id, "loan_account_id should be set by post_init_hook")
        self.assertEqual(self.company.loan_account_id.account_type, "asset_receivable")

    def test_loan_journal_has_no_default_account(self):
        # A receivable/payable account can't be a journal's default account
        # (account.account _check_account_is_bank_journal_bank_account). loan_account_id must
        # stay decoupled from loan_journal_id.default_account_id or this constraint blocks module install.
        self.assertFalse(
            self.company.loan_journal_id.default_account_id,
            "loan_journal_id.default_account_id must stay empty; use company.loan_account_id instead",
        )
