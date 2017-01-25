# -*- coding: utf-8 -*-
from openerp import models, api
from openerp.tools.misc import formatLang


class account_journal(models.Model):
    _inherit = "account.journal"

    @api.multi
    def get_journal_dashboard_datas(self):
        domain_holding_third_checks = [
            # ('payment_method_id.code', '=', 'received_third_check'),
            ('type', '=', 'third_check'),
            ('journal_id', '=', self.id),
            # ('check_state', '=', 'holding')
            ('state', '=', 'holding')
        ]
        domain_handed_issue_checks = [
            # ('payment_method_id.code', '=', 'issue_check'),
            ('type', '=', 'issue_check'),
            ('journal_id', '=', self.id),
            ('state', '=', 'handed')
            # ('check_state', '=', 'handed')
        ]
        handed_checks = self.env['account.check'].search(
            domain_handed_issue_checks)
        holding_checks = self.env['account.check'].search(
            domain_holding_third_checks)
        return dict(
            super(account_journal, self).get_journal_dashboard_datas(),
            num_holding_third_checks=len(holding_checks),
            show_third_checks=(
                'received_third_check' in
                self.inbound_payment_method_ids.mapped('code')),
            show_issue_checks=(
                'issue_check' in
                self.outbound_payment_method_ids.mapped('code')),
            num_handed_issue_checks=len(handed_checks),
            handed_amount=formatLang(
                self.env, sum(handed_checks.mapped('amount')),
                currency_obj=self.currency_id or self.company_id.currency_id),
            holding_amount=formatLang(
                self.env, sum(holding_checks.mapped('amount')),
                currency_obj=self.currency_id or self.company_id.currency_id),
        )
