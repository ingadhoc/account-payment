from odoo import fields, models

ADD_CHECK_CREDIT_PARAM = "l10n_latam_check_ux.add_check_credit"


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _get_on_hand_checks_credit(self, company):
        """Amount of the third party checks on hand, in the currency of ``company``.

<<<<<<< 4592e5f81cc82a8ed38362a4c9b042215da56f49
    @api.depends_context("company")
    @api.depends("add_check_credit")
    def _credit_debit_get(self):
        super()._credit_debit_get()
        for partner in self.filtered("add_check_credit"):
            # sudo + child_of para alinearnos con el _credit_debit_get de core, que agrega los
            # apuntes de toda la jerarquía de compañías (branches) con bypass_access.
            partner_checks = (
                self.env["l10n_latam.check"]
                .sudo()
                .search(
                    [
                        # Partner actual
                        ("partner_id", "=", partner.id),
                        # Filtro por la compañía activa y sus sucursales
                        ("company_id", "child_of", self.env.company.root_id.id),
                        # Filtro On-Hand
                        (
                            "current_journal_id.inbound_payment_method_line_ids.payment_method_id.code",
                            "=",
                            "in_third_party_checks",
                        ),
                        # Cuya fecha de pago sea mayor a la de hoy
                        ("payment_date", ">", fields.Date.context_today(self)),
                    ]
                )
||||||| 8f5864c94fed37498cd37b133a89b0bbe35fb6c7
    @api.depends_context("company")
    @api.depends("add_check_credit")
    def _credit_debit_get(self):
        super()._credit_debit_get()
        for partner in self.filtered("add_check_credit"):
            partner_checks = self.env["l10n_latam.check"].search(
                [
                    # Partner actual
                    ("partner_id", "=", partner.id),
                    # Filtro por empresa actual
                    ("company_id", "=", self.env.company.id),
                    # Filtro On-Hand
                    (
                        "current_journal_id.inbound_payment_method_line_ids.payment_method_id.code",
                        "=",
                        "in_third_party_checks",
                    ),
                    # Cuya fecha de pago sea mayor a la de hoy
                    ("payment_date", ">", fields.Date.context_today(self)),
                ]
=======
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
>>>>>>> d2eeac124ec2ce5d368b12af2e9ef48d10664cdc
            )
        )
        # checks can be in another currency (e.g. USD checks): convert them as the orders to invoice
        return sum(
            payment.currency_id._convert(amount, company.currency_id, company, today) for payment, amount in groups
        )
