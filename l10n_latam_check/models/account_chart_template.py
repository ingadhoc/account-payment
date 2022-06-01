from odoo import models, Command, _
import logging
_logger = logging.getLogger(__name__)
THIRD_CHECKS_COUNTRY_CODES = ["AR"]


class AccountChartTemplate(models.Model):
    _inherit = 'account.chart.template'

    def _create_bank_journals(self, company, acc_template_ref):
        res = super()._create_bank_journals(company, acc_template_ref)

        if company.country_id.code in THIRD_CHECKS_COUNTRY_CODES:
            self.env['account.journal'].create({
                'name': _('Third party checks'),
                'type': 'cash',
                'company_id': company.id,
                'outbound_payment_method_line_ids': [
                    Command.create({'payment_method_id': self.env.ref('l10n_latam_check.account_payment_method_out_third_party_checks').id}),
                ],
                'inbound_payment_method_line_ids': [
                    Command.create({'payment_method_id': self.env.ref('l10n_latam_check.account_payment_method_new_third_party_checks').id}),
                    Command.create({'payment_method_id': self.env.ref('l10n_latam_check.account_payment_method_in_third_party_checks').id}),
                ]})
            self.env['account.journal'].create({
                'name': _('Rejected Third party checks'),
                'type': 'cash',
                'company_id': company.id,
                'outbound_payment_method_line_ids': [
                    Command.create({'payment_method_id': self.env.ref('l10n_latam_check.account_payment_method_out_third_party_checks').id}),
                ],
                'inbound_payment_method_line_ids': [
                    Command.create({'payment_method_id': self.env.ref('l10n_latam_check.account_payment_method_new_third_party_checks').id}),
                    Command.create({'payment_method_id': self.env.ref('l10n_latam_check.account_payment_method_in_third_party_checks').id}),
                ]})
        return res
