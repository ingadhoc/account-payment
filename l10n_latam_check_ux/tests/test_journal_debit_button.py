##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestJournalDebitButton(TransactionCase):
    """A new journal without statements comes with the check debit button enabled.

    Without statements there is no bank line to reconcile the debit against, so
    checks are debited with the button. 'no_statement' is added by
    saas_client_account; when it's missing the test adds it to the selection.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Journal = cls.env.registry["account.journal"]
        get_sources = Journal._get_bank_statements_available_sources

        def _sources(self):
            sources = get_sources(self)
            if "no_statement" not in dict(sources):
                sources = sources + [("no_statement", "No statement")]
            return sources

        cls.startClassPatcher(patch.object(Journal, "_get_bank_statements_available_sources", _sources))

    def _create_journal(self, journal_type, code, **vals):
        return self.env["account.journal"].create({"name": f"Test {code}", "code": code, "type": journal_type, **vals})

    def test_no_statement_journals_enable_debit_button(self):
        for journal_type, code in (("bank", "TNSB"), ("credit", "TNSC")):
            with self.subTest(journal_type=journal_type):
                journal = self._create_journal(journal_type, code, bank_statements_source="no_statement")
                self.assertTrue(journal.check_add_debit_button)

    def test_other_journals_keep_debit_button_disabled(self):
        bank = self._create_journal("bank", "TUNB", bank_statements_source="undefined")
        cash = self._create_journal("cash", "TCSH")
        self.assertFalse(bank.check_add_debit_button)
        self.assertFalse(cash.check_add_debit_button)
