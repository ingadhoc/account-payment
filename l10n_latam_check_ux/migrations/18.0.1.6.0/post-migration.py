import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("Forzamos la actualización de los l10n_latam_move_check_ids_operation_date")
    cr.execute("""
        UPDATE account_payment
        SET l10n_latam_move_check_ids_operation_date = create_date
        WHERE payment_method_line_id IN (
            SELECT id FROM account_payment_method_line
            WHERE payment_method_id IN (
                SELECT id FROM account_payment_method
                WHERE code IN (
                    'out_third_party_checks',
                    'in_third_party_checks',
                    'new_third_party_checks',
                    'own_checks',
                    'return_third_party_checks'
                )
            )
        )
        AND state NOT IN ('draft', 'canceled')
        AND l10n_latam_move_check_ids_operation_date IS NULL
    """)
