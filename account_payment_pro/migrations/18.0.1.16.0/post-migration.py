import logging

from odoo.tools import sql

_logger = logging.getLogger(__name__)

TABLE = "account_move_line_payment_to_pay_rel"
# Name Postgres gives to the unnamed index Odoo creates on m2m tables
INDEX = "account_move_line_payment_to_pay__to_pay_line_id_payment_id_idx"


def migrate(cr, version):
    """Deja account_move_line_payment_to_pay_rel como la crea Odoo.

    En las bases que vienen de payment group, la UL 1026 crea la tabla antes de instalar el módulo, sin
    clave primaria ni índices, y Odoo no la completa porque ya existe. Cada lectura o borrado por pago
    o por apunte recorre la tabla entera.

    Si la tabla no tiene clave primaria, se borran las filas con nulos y las repetidas (queda una de
    cada par) y se agregan la clave primaria y el índice con los mismos nombres que usa Odoo. Las
    tablas que creó Odoo no cambian.
    """
    if not sql.table_exists(cr, TABLE):
        return
    cr.execute(
        "SELECT 1 FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'p'",
        [TABLE],
    )
    if not cr.rowcount:
        cr.execute(
            "DELETE FROM account_move_line_payment_to_pay_rel WHERE payment_id IS NULL OR to_pay_line_id IS NULL"
        )
        _logger.info("account_payment_pro: %s rows with nulls deleted from %s", cr.rowcount, TABLE)
        cr.execute(
            """
            DELETE FROM account_move_line_payment_to_pay_rel a
             USING account_move_line_payment_to_pay_rel b
             WHERE a.payment_id = b.payment_id
               AND a.to_pay_line_id = b.to_pay_line_id
               AND a.ctid > b.ctid
            """
        )
        _logger.info("account_payment_pro: %s duplicated rows deleted from %s", cr.rowcount, TABLE)
        cr.execute("ALTER TABLE account_move_line_payment_to_pay_rel ADD PRIMARY KEY (payment_id, to_pay_line_id)")
        cr.execute(
            "COMMENT ON TABLE account_move_line_payment_to_pay_rel IS 'RELATION BETWEEN account_payment AND account_move_line'"
        )
        _logger.info("account_payment_pro: primary key added to %s", TABLE)
    sql.create_index(cr, INDEX, TABLE, ["to_pay_line_id", "payment_id"])
