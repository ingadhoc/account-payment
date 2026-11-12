from odoo import fields, models

ADD_CHECK_CREDIT_PARAM = "l10n_latam_check_ux.add_check_credit"


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _get_on_hand_checks_credit(self, company):
        """Amount of the third party checks on hand, in the currency of ``company``.

        The customer handed them over, so its debt is settled in the books (``credit``), but the
        money is not in the bank until the check is deposited, whether it is due or not. The credit limit warning adds them up
        on top of the accounting debt, the same way it adds the orders to invoice.

        ``credit`` is left untouched on purpose: it must match the partner ledger.

        Checks of every company of the hierarchy (branches) are taken, the same way the standard
        ``credit`` adds up the journal items. Returns 0 when the global setting is off.
        """
        self.ensure_one()
        if not self.env["ir.config_parameter"].sudo().get_param(ADD_CHECK_CREDIT_PARAM):
            return 0.0
        today = fields.Date.context_today(self)
        groups = (
            self.env["l10n_latam.check"]
            .sudo()
            ._read_group(
                [
                    ("payment_id.partner_id.commercial_partner_id", "=", self.commercial_partner_id.id),
                    ("company_id", "child_of", company.root_id.id),
                    # on hand: the check sits in a third party checks journal. Deposited, endorsed or
                    # rejected checks (returned to the customer, who owes them again) leave it.
                    (
                        "current_journal_id.inbound_payment_method_line_ids.payment_method_id.code",
                        "=",
                        "in_third_party_checks",
                    ),
                ],
                groupby=["payment_id"],
                aggregates=["amount:sum"],
            )
        )
        # checks can be in another currency (e.g. USD checks): convert them as the orders to invoice
        return sum(
            payment.currency_id._convert(amount, company.currency_id, company, today) for payment, amount in groups
        )
