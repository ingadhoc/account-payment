from odoo.addons.account.controllers.portal import PortalAccount
from odoo.http import request


class PortalAccountInherit(PortalAccount):
    # Obtiene el dominio de facturas vencidas y excluye las que tienen
    # pagos online pendientes (no manual/transferencia); esta busqueda
    # es necesaria porque el usuario portal no accede a payment.transaction.
    def _get_overdue_invoices_domain(self, partner_id=None):
        domain = super()._get_overdue_invoices_domain(partner_id=partner_id)
        move_ids = request.env["account.move"].search(domain).ids
        ignored_moves = (
            request.env["payment.transaction"]
            .sudo()
            .search(
                [
                    ("invoice_ids", "in", move_ids),
                    ("provider_code", "not in", ["manual", "transfer"]),
                    ("state", "=", "pending"),
                ]
            )
            .mapped("invoice_ids")
            .ids
        )
        if ignored_moves:
            domain += [("id", "not in", ignored_moves)]
        return domain
