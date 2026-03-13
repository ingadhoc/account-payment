from odoo import http, _
from odoo.addons.account.controllers.portal import PortalAccount


class PortalAccountInherit(PortalAccount):

    @http.route(['/my/invoices/<int:invoice_id>'], type='http', auth="public", website=True)
    def portal_my_invoice_detail(self, invoice_id, access_token=None, report_type=None, download=False, **kw):
        # Solo deberian poder cancelar los usuarios registrados con acceso a la Inv 
        # por eso chequeo el acceso sin el access_token
        try:
            invoice_sudo = self._document_check_access('account.move', invoice_id, None)
        except (AccessError, MissingError):
            return super().portal_my_invoice_detail(invoice_id = invoice_id, access_token=access_token, report_type=report_type, download=download, **kw)

        if not report_type and 'cancel_pending_transactions' in kw:
            invoice_sudo.get_portal_last_transaction()._set_canceled(_('Cancel from portal'))
        return super().portal_my_invoice_detail(invoice_id = invoice_id, access_token=access_token, report_type=report_type, download=download, **kw)

