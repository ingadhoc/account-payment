# -*- coding: utf-8 -*-
from odoo.exceptions import Warning
from odoo import models, fields, api, _
import logging
_logger = logging.getLogger(__name__)


class account_check_wizard(models.TransientModel):
    _name = 'account.check.wizard'

    @api.model
    def _get_company_id(self):
        active_ids = self._context.get('active_ids', [])
        checks = self.env['account.check'].browse(active_ids)
        company_ids = [x.company_id.id for x in checks]
        if len(set(company_ids)) > 1:
            raise Warning(_('All checks must be from the same company!'))
        return self.env['res.company'].search(
            [('id', 'in', company_ids)], limit=1)

    journal_id = fields.Many2one(
        'account.journal',
        'Journal',
        domain="[('company_id','=',company_id), "
        "('type', 'in', ['cash', 'bank']), "
        "('outbound_payment_method_ids', 'not in', [ 7, 8]), "
        "('inbound_payment_method_ids', 'not in', [3, 6])]"


        #"('payment_subtype', 'not in', ['issue_check', 'third_check'])]",
    )
    account_id = fields.Many2one(
        'account.account',
        'Account',
        related='journal_id.default_debit_account_id',
        store=True,
#        domain="[('company_id','=',company_id), "
#        "('type', 'in', ('other', 'liquidity'))]",
#        readonly=True
    )
    date = fields.Date(
        'Date', required=True, default=fields.Date.context_today
    )
    action_type = fields.Char(
        'Action type passed on the context', required=True
    )
    company_id = fields.Many2one(
        'res.company',
        'Company',
        required=True,
        default=_get_company_id
    )
            
    @api.multi
    def action_confirm(self):
        self.ensure_one()

        for check in self.env['account.check'].browse(
                self._context.get('active_ids', [])):
            if self.action_type == 'deposit':
                self.bank_deposited(check, self.journal_id, self.date)
            elif self.action_type == 'bank_reject':
                self.bank_rejected(check, self.date)    
            
    @api.multi
    def bank_deposited(self, check, journal_id, date):
        self.ensure_one()
        if check.state in ['holding']:
            vals = check.get_bank_vals(
                'bank_deposited', journal_id, date)
            move = self.env['account.move'].create(vals)
            check._add_operation('deposited', move)
            
    @api.multi
    def bank_rejected(self, check, journal_id, date):
        self.ensure_one()
        if check.state in ['deposited']:
            vals = check.get_bank_vals(
                'bank_rejected', date)
            move = self.env['account.move'].create(vals)
            check._add_operation('rejected', move)
