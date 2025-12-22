from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    add_check_credit = fields.Boolean("Agregar Crédito de Cheques")

    @api.depends_context("company")
    @api.depends("add_check_credit")
    def _credit_debit_get(self):
        super()._credit_debit_get()
        partners_to_check = self.filtered("add_check_credit")
        if not partners_to_check:
            return
        
        # Usar read_group para mejor performance (una sola query)
        checks_data = self.env["l10n_latam.check"].read_group(
            domain=[
                # Partners filtrados
                ("partner_id", "in", partners_to_check.ids),
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
            ],
            fields=["amount:sum"],
            groupby=["partner_id"],
        )
        
        # Crear diccionario con los montos por partner
        checks_by_partner = {
            data["partner_id"][0]: data["amount"] for data in checks_data
        }
        
        # Actualizar el crédito de cada partner
        for partner in partners_to_check:
            partner.credit += checks_by_partner.get(partner.id, 0.0)
