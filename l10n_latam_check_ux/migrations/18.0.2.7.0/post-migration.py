import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    checks = env["l10n_latam.check"].search(
        [
            ("payment_method_line_id.code", "=", "own_checks"),
            ("payment_id.state", "not in", ["draft", "cancel"]),
            ("outstanding_line_id", "=", False),
            ("create_date", ">=", "2026-02-10"),
            ("create_date", "<=", "2026-02-27"),
        ]
    )

    for check in checks:
        journal = check.payment_id.journal_id
        account = journal.outbound_payment_method_line_ids.filtered(
            lambda x: x.name == check.payment_method_line_id.name
            and x.payment_method_id.id == check.payment_method_line_id.payment_method_id.id
        ).payment_account_id
        outstanding_line_id = check.payment_id.move_id.line_ids.filtered(lambda x: x.account_id.id == account.id)
        check.write({"outstanding_line_id": outstanding_line_id.id, "issue_state": "handed"})

    env.cr.commit()
