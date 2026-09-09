import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Fix the checks left on the wrong company.

    Until this version the core ``related`` on ``company_id`` survived the field
    redefinition, so ``_compute_company_id`` never ran on its own and the checks
    kept the company of an operation that was later reset to draft or deleted.
    Such a check matches no payment domain and is invisible from every company.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    # candidates: the company differs from the payment's one, either because an
    # operation legitimately moved the check or because the value got stuck
    cr.execute(
        """
        SELECT c.id
          FROM l10n_latam_check c
          JOIN account_payment p ON p.id = c.payment_id
         WHERE c.company_id IS DISTINCT FROM p.company_id
        """
    )
    candidates = env["l10n_latam.check"].browse([row[0] for row in cr.fetchall()])
    to_fix = env["l10n_latam.check"]
    for check in candidates:
        expected = (check._get_last_operation() or check.payment_id).company_id
        if expected and check.company_id != expected:
            _logger.info(
                "Check %s (id %s) moves from company %s to %s",
                check.name,
                check.id,
                check.company_id.display_name,
                expected.display_name,
            )
            to_fix |= check
    if not to_fix:
        _logger.info("No checks left on the wrong company")
        return
    to_fix._compute_company_id()
    env.flush_all()
    _logger.info("Fixed the company of %s checks", len(to_fix))
