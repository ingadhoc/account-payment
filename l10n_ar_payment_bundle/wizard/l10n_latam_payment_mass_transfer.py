from odoo import api, fields, models


class L10nLatamPaymentMassTransfer(models.TransientModel):
    _inherit = "l10n_latam.payment.mass.transfer"

    destination_journal_domain = fields.Json(
        compute="_compute_destination_journal_domain",
        readonly=True,
    )

    destination_journal_id = fields.Many2one(
        domain="destination_journal_domain",
    )

    @api.depends("journal_id", "company_id")
    def _compute_destination_journal_domain(self):
        """Exclude bundle journals from destination journal selection."""
        for rec in self:
            # Keep the whole company tree: cross-branch transfers are rejected on confirm,
            # which tells the user to use the internal transfer instead.
            rec.destination_journal_domain = [
                ("type", "in", ("bank", "cash")),
                ("id", "!=", rec.journal_id.id),
                ("company_id", "child_of", rec.company_id.root_id.id),
                ("inbound_payment_method_line_ids", "not any", [("payment_method_id.code", "=", "payment_bundle")]),
                ("outbound_payment_method_line_ids", "not any", [("payment_method_id.code", "=", "payment_bundle")]),
            ]
