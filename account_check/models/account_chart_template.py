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
