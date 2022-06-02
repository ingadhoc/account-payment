from openupgradelib import openupgrade

import logging
_logger = logging.getLogger(__name__)


_xmlid_renames = [
    ('l10n_latam_check.account_payment_method_new_third_checks', 'l10n_latam_check.account_payment_method_new_third_party_checks'),
    ('l10n_latam_check.account_payment_method_in_third_checks', 'l10n_latam_check.account_payment_method_in_third_party_checks'),
    ('l10n_latam_check.account_payment_method_out_third_checks', 'l10n_latam_check.account_payment_method_out_third_party_checks'),
]


@openupgrade.migrate()
def migrate(env, version):
    _logger.debug('Running migrate script for l10n_ar')
    openupgrade.rename_xmlids(env.cr, _xmlid_renames)
