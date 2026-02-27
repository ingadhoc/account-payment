import logging

from odoo import Command, api, models

_logger = logging.getLogger(__name__)


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @api.model
    def _install_account_cashbox_bundle_demo(self, companies):
        """
        Crea demo data minimalista para probar account_cashbox_bundle.
        Cubre los casos de uso:
        1. Diarios bundle no deben estar en cashbox configuration
        2. Main payments no requieren cashbox session
        3. Child payments sí requieren session cuando el usuario lo requiere

        Nota: El diario bundle (payment_bundle_journal) ya es creado por l10n_ar_payment_bundle,
        por lo que no es necesario crearlo aquí.

        Se crea solo para la compañía Responsable Inscripto (base.company_ri).
        """
        for company in companies:
            _logger.info("Creating cashbox bundle demo data for company: %s", company.name)
            self = self.with_company(company)

            demo_data = {
                "res.partner": self._cashbox_bundle_demo_partners(company),
                "res.users": self._cashbox_bundle_demo_users(company),
                "ir.sequence": self._cashbox_bundle_demo_sequences(company),
                "account.cashbox": self._cashbox_bundle_demo_cashboxes(company),
            }

            self.sudo()._load_data(demo_data)

    @api.model
    def _cashbox_bundle_demo_partners(self, company):
        """Create minimal partner for payments"""
        return {
            "demo_partner_cashbox": {
                "name": "Demo Cashbox Partner",
                "company_id": company.id,
            },
        }

    @api.model
    def _cashbox_bundle_demo_users(self, company):
        """Create user that requires cashbox session"""
        return {
            "demo_user_requires_cashbox": {
                "name": "Demo Cashbox User",
                "login": "demo_cashbox_user",
                "email": "demo_cashbox@test.com",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "requiere_account_cashbox_session": True,
            },
        }

    @api.model
    def _cashbox_bundle_demo_sequences(self, company):
        """Create sequence for cashbox sessions"""
        return {
            "account_cashbox_sequence": {
                "name": "Cashbox Sessions",
                "code": "account.cashbox.session",
                "prefix": "CASH/%(year)s/",
                "padding": 3,
                "company_id": company.id,
            },
        }

    @api.model
    def _cashbox_bundle_demo_cashboxes(self, company):
        """Create cashbox with existing journals (excluding bundle journal)"""
        # Find existing cash and bank journals for the company
        existing_cash_journals = self.env["account.journal"].search(
            [("type", "=", "cash"), ("company_id", "=", company.id)], limit=1
        )

        existing_bank_journals = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", company.id)], limit=1
        )

        # Build journal_ids list with existing journals
        journal_ids = []
        if existing_cash_journals:
            journal_ids.append((4, existing_cash_journals.id))
        if existing_bank_journals:
            journal_ids.append((4, existing_bank_journals.id))

        return {
            "demo_cashbox_main": {
                "name": "Demo Cashbox",
                "company_id": company.id,
                "journal_ids": journal_ids,
                "sequence_id": "account_cashbox_sequence",
            },
        }
