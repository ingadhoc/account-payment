def migrate(cr, version):
    cr.execute("COMMENT ON INDEX l10n_latam_check_unique IS 'index marked to upgrade'")
