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
            base_domain = [
                ("type", "in", ("bank", "cash")),
                ("id", "!=", rec.journal_id.id),
                ("company_id", "=", rec.company_id.id),
            ]

            # Exclude both inbound and outbound bundle journals
            bundle_journal_inbound = rec.company_id._get_bundle_journal("inbound")
            bundle_journal_outbound = rec.company_id._get_bundle_journal("outbound")

            if bundle_journal_inbound:
                base_domain.append(("id", "!=", bundle_journal_inbound))
            if bundle_journal_outbound:
                base_domain.append(("id", "!=", bundle_journal_outbound))

            rec.destination_journal_domain = base_domain
