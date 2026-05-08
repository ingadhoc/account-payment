from collections import defaultdict

from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _get_name_receipt_report(self, report_xml_id):
        """Return the QWeb template to use for the payment receipt.

        Kept generic in account_payment_pro so localizations can override it,
        similar to l10n_latam_invoice_document's invoice report selection.
        """
        self.ensure_one()
        return report_xml_id

    def _get_payment_bundle_key(self):
        """Default grouping key: one receipt per payment.

        Bundle modules can override this key under specific contexts.
        """
        self.ensure_one()
        return self.id

    def _get_payment_bundles(self):
        """Return payment recordsets grouped by receipt.

        The default implementation does not group payments together. It exists
        so modules such as l10n_ar_payment_bundle can extend it without needing
        a localization module to provide the base method.
        """
        bundles = defaultdict(lambda: self.env["account.payment"])
        for payment in self:
            bundles[payment._get_payment_bundle_key()] += payment
        return bundles

    def _select_bundle(self, bundles):
        """Select the receipt payment set for the current payment."""
        self.ensure_one()
        return bundles.get(self._get_payment_bundle_key(), self)
