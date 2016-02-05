# -*- encoding: utf-8 -*-


def migrate(cr, version):
    print 'Migrating create_date to confirmation_date'
    if not version:
        return
    table = 'account_voucher'
    source_field = "create_date"
    target_field = "confirmation_date"
    condition = "state NOT IN ('cancel', 'draft')"
    cr.execute(
        "UPDATE %s SET %s = %s WHERE %s" % (
            table, target_field, source_field, condition))
