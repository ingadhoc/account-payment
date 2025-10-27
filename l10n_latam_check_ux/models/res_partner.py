from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    add_check_credit = fields.Boolean("Agregar Crédito de Cheques")

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
            )

            partner.credit += sum(partner_checks.mapped("amount"))
