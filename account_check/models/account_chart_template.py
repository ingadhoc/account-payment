# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, api, fields
import logging
_logger = logging.getLogger(__name__)


class AccountChartTemplate(models.Model):
    _inherit = 'account.chart.template'

    rejected_check_account_id = fields.Many2one(
        'account.account.template',
        'Rejected Check Account',
        # required=True,
        help='Rejection Checks account, for eg. "Rejected Checks"',
        # domain=[('type', 'in', ['other'])],
    )
    deferred_check_account_id = fields.Many2one(
        'account.account.template',
        'Deferred Check Account',
        # required=True,
        help='Deferred Checks account, for eg. "Deferred Checks"',
        # domain=[('type', 'in', ['other'])],
    )
    holding_check_account_id = fields.Many2one(
        'account.account.template',
        'Holding Check Account',
        # required=True,
        help='Holding Checks account for third checks, '
        'for eg. "Holding Checks"',
        # domain=[('type', 'in', ['other'])],
    )

    # @api.multi
    # def _install_template(
    #         self, company, code_digits=None, transfer_account_id=None,
    #         obj_wizard=None, acc_ref=None, taxes_ref=None):
    #     account_ref, taxes_ref = super(
    #         AccountChartTemplate, self)._install_template(
    #             self, company, code_digits=code_digits,
    #             transfer_account_id=transfer_account_id,
    #             obj_wizard=obj_wizard, acc_ref=acc_ref, taxes_ref=taxes_ref)
    @api.multi
    def _load_template(
            self, company, code_digits=None, transfer_account_id=None,
            account_ref=None, taxes_ref=None):
        account_ref, taxes_ref = super(
            AccountChartTemplate, self)._load_template(
                company,
                code_digits=code_digits,
                transfer_account_id=transfer_account_id,
                account_ref=account_ref,
                taxes_ref=taxes_ref)
        for field in [
                'rejected_check_account_id',
                'deferred_check_account_id',
                'holding_check_account_id']:
            account_field = self[field]
            # TODO we should send it in the context and overwrite with
            # lower hierichy values
            if account_field:
                company.update({field: account_ref[account_field.id]})
        return account_ref, taxes_ref

    @api.model
    def _prepare_all_journals(
            self, acc_template_ref, company, journals_dict=None):
        """
        Inherit this function in order to add checks to cash and bank
        journals. This is because usually will be installed before chart loaded
        and they will be disable by default
        """
        journal_data = super(
            AccountChartTemplate, self)._prepare_all_journals(
            acc_template_ref, company, journals_dict)
        for vals_journal in journal_data:
            if vals_journal['type'] == 'bank':
                issue_checks = self.env.ref(
                    'account_check.account_payment_method_issue_check')
                vals_journal['outbound_payment_method_ids'] = [
                    (4, issue_checks.id, None)],
            elif vals_journal['type'] == 'cash':
                received_third_check = self.env.ref(
                    'account_check.'
                    'account_payment_method_received_third_check')
                delivered_third_check = self.env.ref(
                    'account_check.'
                    'account_payment_method_delivered_third_check')

                vals_journal['inbound_payment_method_ids'] = [
                    (4, received_third_check.id, None)]
                vals_journal['outbound_payment_method_ids'] = [
                    (4, delivered_third_check.id, None)]
        return journal_data
