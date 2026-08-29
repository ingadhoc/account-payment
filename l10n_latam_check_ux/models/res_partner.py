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

        self.env.cr.execute(
            """
            SELECT
                ap.partner_id,
                SUM(
                    CASE
                        WHEN ap.currency_id = %(company_currency_id)s
                        THEN lc.amount
                        ELSE lc.amount * COALESCE(
                            (SELECT rate FROM res_currency_rate
                             WHERE currency_id = %(company_currency_id)s
                             AND name <= lc.payment_date
                             AND company_id = lc.company_id
                             ORDER BY name DESC LIMIT 1),
                            1.0
                        ) / COALESCE(
                            (SELECT rate FROM res_currency_rate
                             WHERE currency_id = ap.currency_id
                             AND name <= lc.payment_date
                             AND company_id = lc.company_id
                             ORDER BY name DESC LIMIT 1),
                            1.0
                        )
                    END
                ) as total_amount
            FROM l10n_latam_check lc
            INNER JOIN account_payment ap on ap.id = lc.payment_id
            INNER JOIN account_journal aj ON aj.id = lc.current_journal_id
            INNER JOIN account_payment_method_line apml ON apml.journal_id = aj.id
            INNER JOIN account_payment_method apm ON apm.id = apml.payment_method_id
            WHERE ap.partner_id IN %(partner_ids)s
                AND lc.company_id = %(company_id)s
                AND apm.code = 'in_third_party_checks'
                AND lc.payment_date > %(today)s
            GROUP BY ap.partner_id
            """,
            {
                "partner_ids": tuple(partners_to_check.ids),
                "company_id": self.env.company.id,
                "company_currency_id": self.env.company.currency_id.id,
                "today": fields.Date.context_today(self),
            },
        )
        # Crear diccionario con los montos convertidos por partner
        checks_by_partner = {row[0]: row[1] for row in self.env.cr.fetchall()}

        # Actualizar el crédito de cada partner
        for partner in partners_to_check:
            partner.credit += checks_by_partner.get(partner.id, 0.0)
