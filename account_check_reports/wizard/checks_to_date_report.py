# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, api, fields


class account_check_to_date_report_wizard(models.TransientModel):
    _name = 'account.check.to_date.report.wizard'

    journal_id = fields.Many2one(
        'account.journal',
        string='Diario',
        domain=[('payment_subtype', '=', 'issue_check')],
    )
    to_date = fields.Date(
        'Hasta Fecha',
        required=True,
        default=fields.Date.today,
    )

    @api.multi
    def action_confirm(self):
        self.ensure_one()
        issue_domain = [
            ('type', '=', 'issue_check'),
            ('state', 'not in', ['draft', 'cancel', 'changed', 'returned']),
            ('issue_date', '<=', self.to_date),
            # todavia no debitado
            '|',
            ('debit_account_move_id', '=', False),
            # o no debitado en la fecha
            ('debit_account_move_id.date', '>', self.to_date),
        ]
        if self.journal_id:
            issue_domain.append(('journal_id', '=', self.journal_id.id))
        issue_checks = self.env['account.check'].search(issue_domain)

        third_domain = [
            ('type', '=', 'third_check'),
            ('state', 'not in', ['draft', 'cancel', 'changed', 'returned']),
            ('issue_date', '<=', self.to_date),
            # todavia no debitado
            '|',
            ('third_handed_voucher_id.move_id.date', '>', self.to_date),
            '|',
            ('deposit_date', '>', self.to_date),
            '&',
            ('third_handed_voucher_id', '=', False),
            ('deposit_date', '=', False),
            # o no debitado en la fecha
        ]
        if self.journal_id:
            third_domain.append(('journal_id', '=', self.journal_id.id))
        third_checks = self.env['account.check'].search(third_domain)

        return self.env['report'].with_context(
            issue_check_ids=issue_checks.ids,
            third_check_ids=third_checks.ids,).get_action(
            self, 'account_checks_to_date_report')
