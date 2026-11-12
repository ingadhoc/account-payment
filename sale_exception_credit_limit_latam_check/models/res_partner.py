from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    credit_with_confirmed_orders = fields.Monetary(
        help="Total amount this customer owes you (including not invoiced confirmed sale orders, draft invoices "
        "and, when enabled in the settings, the third party checks on hand).",
    )

    @api.depends_context("company")
    def _compute_credit_with_confirmed_orders(self):
        super()._compute_credit_with_confirmed_orders()
        # same condition as the base compute, which leaves the field at 0 without a partner limit
        for rec in self.filtered("use_partner_credit_limit"):
            rec.credit_with_confirmed_orders += rec.commercial_partner_id._get_on_hand_checks_credit(self.env.company)
