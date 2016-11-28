# -*- coding: utf-8 -*-
from openerp import models, api


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
        return dict(
            super(account_journal, self).get_journal_dashboard_datas(),
            num_holding_third_checks=len(self.env['account.check'].search(
                domain_holding_third_checks)),
            show_third_checks=(
                'received_third_check' in
                self.inbound_payment_method_ids.mapped('code')),
            show_issue_checks=(
                'issue_check' in
                self.outbound_payment_method_ids.mapped('code')),
            num_handed_issue_checks=len(self.env['account.check'].search(
                domain_handed_issue_checks)),
        )
