def migrate(cr, version):
    """The 'electronic_pending' value is no longer added to account.move payment_state,
    it is only exposed on status_in_payment. Restore the real payment state on the
    invoices that were stamped with it, otherwise they keep an orphan value."""
    cr.execute("UPDATE account_move SET payment_state = 'not_paid' WHERE payment_state = 'electronic_pending'")
