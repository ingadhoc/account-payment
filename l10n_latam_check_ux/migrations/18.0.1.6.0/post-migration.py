import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("Forzamos la actualización de los l10n_latam_move_check_ids_operation_date")
    cr.execute("""
        UPDATE account_payment
        SET l10n_latam_move_check_ids_operation_date = create_date
        WHERE l10n_latam_move_check_ids_operation_date IS NULL
    """)
