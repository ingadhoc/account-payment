import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info(
        "Migrando loan_account_id: lo separamos del default_account_id del loan_journal_id "
        "(un journal no puede tener una cuenta receivable/payable como default_account_id, "
        "ver account.account _check_account_is_bank_journal_bank_account)"
    )
    cr.execute("""
        UPDATE res_company company
        SET loan_account_id = journal.default_account_id
        FROM account_journal journal
        WHERE journal.id = company.loan_journal_id
          AND journal.default_account_id IS NOT NULL
          AND company.loan_account_id IS NULL
    """)
    cr.execute("""
        UPDATE account_journal journal
        SET default_account_id = NULL
        FROM res_company company
        WHERE company.loan_journal_id = journal.id
          AND journal.default_account_id IS NOT NULL
    """)
