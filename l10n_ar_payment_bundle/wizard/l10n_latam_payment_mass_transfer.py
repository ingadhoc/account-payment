from odoo import api, fields, models


class L10nLatamPaymentMassTransfer(models.TransientModel):
    _inherit = "l10n_latam.payment.mass.transfer"

    to_journal_domain = fields.Json(
        compute="_compute_to_journal_domain",
        readonly=True,
    )

    to_journal_id = fields.Many2one(
        domain="to_journal_domain",
    )

    @api.depends("from_journal_id", "from_journal_currency_id", "company_ids")
    def _compute_to_journal_domain(self):
        """Native destination domain excluding the inbound and outbound bundle journals."""
        for rec in self:
            companies = rec.company_ids | rec.from_journal_id.company_id
            bundle_journal_ids = [
                journal_id
                for company in companies
                for payment_type in ("inbound", "outbound")
                if (journal_id := company._get_bundle_journal(payment_type))
            ]
            rec.to_journal_domain = [
                ("type", "in", ("bank", "cash")),
                ("id", "!=", rec.from_journal_id.id),
                ("currency_id", "=", rec.from_journal_currency_id.id),
                ("id", "not in", bundle_journal_ids),
            ]
