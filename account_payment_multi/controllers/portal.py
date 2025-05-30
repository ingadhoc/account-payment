from collections import Counter

from odoo import _, fields, http
from odoo.addons.account.controllers.portal import PortalAccount
from odoo.addons.payment.controllers import portal as payment_portal
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request, route


class PaymentPortal(payment_portal.PaymentPortal):
    def _get_selected_invoices_domain(self, due_date, partner_id=None):
        return [
            ("state", "not in", ("cancel", "draft")),
            ("move_type", "in", ("out_invoice", "out_receipt")),
            ("payment_state", "not in", ("in_payment", "paid")),
            ("partner_id", "=", partner_id or request.env.user.partner_id.id),
            ("invoice_date_due", "<=", due_date),
        ]

    @http.route(["/my/invoices/selected"], type="http", auth="public", methods=["GET"], website=True, sitemap=False)
    def portal_my_selected_invoices(self, **kw):
        try:
            request.env["account.move"].check_access_rights("read")
        except (AccessError, MissingError):
            return request.redirect("/my")

        invoice_id = int(kw.get("invoice_id"))
        invoice = request.env["account.move"].browse(invoice_id)
        due_date = invoice.invoice_date_due
        invoice_date = invoice.invoice_date

        # Initial selection by due_date
        selected_invoices = request.env["account.move"].search(self._get_selected_invoices_domain(due_date=due_date))

        # If more than one with the due_date, filter by invoice_date <= invoice_date
        if selected_invoices.mapped("invoice_date_due").count(due_date) > 1:
            selected_invoices = selected_invoices.filtered(
                lambda x: not (x.invoice_date_due == due_date and x.invoice_date > invoice_date)
            )

            # Count how many times the combination of due_date and invoice_date appears
            combo_counter = Counter((inv.invoice_date_due, inv.invoice_date) for inv in selected_invoices)
            if combo_counter[(due_date, invoice_date)] > 1:
                selected_invoices = selected_invoices.filtered(
                    lambda x: not (
                        x.invoice_date_due == due_date and x.invoice_date == invoice_date and x.id > invoice_id
                    )
                )

        values = self._selected_invoices_get_page_view_values(selected_invoices, **kw)
        return (
            request.render("account_payment_multi.portal_selected_invoices_page", values)
            if "payment" in values
            else request.redirect("/my/invoices/selected")
        )

    def _selected_invoices_get_page_view_values(self, selected_invoices, **kwargs):
        values = {"page_name": "selected_invoices"}

        if len(selected_invoices) == 0:
            return values

        first_invoice = selected_invoices[0]
        partner = first_invoice.partner_id
        company = first_invoice.company_id
        currency = first_invoice.currency_id

        if any(invoice.partner_id != partner for invoice in selected_invoices):
            raise ValidationError(_("Selected invoices should share the same partner."))
        if any(invoice.company_id != company for invoice in selected_invoices):
            raise ValidationError(_("Selected invoices should share the same company."))
        if any(invoice.currency_id != currency for invoice in selected_invoices):
            raise ValidationError(_("Selected invoices should share the same currency."))

        total_amount = sum(selected_invoices.mapped("amount_total"))
        amount_residual = sum(selected_invoices.mapped("amount_residual"))
        batch_name = (
            company.get_next_batch_payment_communication() if len(selected_invoices) > 1 else first_invoice.name
        )

        values["payment"] = {
            "date": fields.Date.today(),
            "reference": batch_name,
            "amount": total_amount,
            "currency": currency,
        }

        common_view_values = self._get_common_page_view_values(
            invoices_data={
                "partner": partner,
                "company": company,
                "total_amount": total_amount,
                "currency": currency,
                "amount_residual": amount_residual,
                "payment_reference": batch_name,
                "landing_route": "/my/invoices/",
                "transaction_route": "/invoice/transaction/selected",
            },
            multi=True,
            **kwargs,
        )

        values |= common_view_values
        return values

    def _get_common_page_view_values(self, invoices_data, access_token=None, **kwargs):
        values = super()._get_common_page_view_values(invoices_data, access_token=access_token, **kwargs)
        values["amount"] = invoices_data["amount_residual"]

        return values

    def _get_extra_payment_form_values(self, invoice_id=None, access_token=None, **kwargs):
        form_values = super()._get_extra_payment_form_values(invoice_id=invoice_id, access_token=access_token, **kwargs)
        if kwargs.get("multi"):
            form_values.update(
                {
                    "transaction_route": f"/invoice/transaction/selected/{invoice_id}",
                }
            )

        return form_values

    @route("/invoice/transaction/selected/<int:invoice_id>", type="json", auth="public")
    def selected_invoices_transaction(self, payment_reference, **kwargs):
        """Create a draft transaction for selected invoices and return its processing values.

        :param str payment_reference: The reference to the current payment
        :param dict kwargs: Locally unused data passed to `_create_transaction`
        :return: The mandatory values for the processing of the transaction
        :rtype: dict
        :raise: ValidationError if the user is not logged in, or all the selected invoices don't share the same currency.
        """

        logged_in = not request.env.user._is_public()
        if not logged_in:
            raise ValidationError(_("Please log in to pay your selected invoices"))
        partner = request.env.user.partner_id

        invoice_id = int(kwargs.get("invoice_id"))
        due_date = request.env["account.move"].browse(invoice_id).invoice_date_due

        selected_invoices = request.env["account.move"].search(self._get_selected_invoices_domain(due_date))
        currencies = selected_invoices.mapped("currency_id")
        if not all(currency == currencies[0] for currency in currencies):
            raise ValidationError(
                _("Impossible to pay all the selected invoices if they don't share the same currency.")
            )
        self._validate_transaction_kwargs(kwargs, ("invoice_id", "access_token"))
        return self._process_transaction(
            partner.id, currencies[0].id, selected_invoices.ids, payment_reference, **kwargs
        )


class PortalAccountCustom(PortalAccount):
    def _get_account_searchbar_sortings(self):
        res = super()._get_account_searchbar_sortings()
        res["duedate"]["order"] = "invoice_date_due desc, invoice_date desc, id desc"

        return res

    def _prepare_my_invoices_values(
        self, page, date_begin, date_end, sortby, filterby, domain=None, url="/my/invoices"
    ):
        return super()._prepare_my_invoices_values(
            page=page,
            date_begin=date_begin,
            date_end=date_end,
            sortby="duedate",
            filterby=filterby,
            domain=domain,
            url=url,
        )
