# -*- encoding: utf-8 -*-


def migrate(cr, version):
    print 'Migrating create_date to confirmation_date'
    if not version:
        return
    # if we are updating we are supose to be using duble validation
    cr.execute(
        "UPDATE res_company SET double_validation = True")
