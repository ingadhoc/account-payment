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
            elif self.action_type == 'return':
                self.returned(check, self.date)
            elif self.action_type == 'revert_return':
                self.revert_return(check, self.date)
            elif self.action_type == 'claim':
                self.claim(check, self.date)
            elif self.action_type == 'bank_debit':
                self.bank_debit(check, self.date)
                
                
    @api.multi
    def bank_debit(self, check, date):
        self.ensure_one()
        if check.state in ['handed']:
            vals = check.get_bank_vals(
                'bank_debit', check.checkbook_id.debit_journal_id, date)
            move = self.env['account.move'].create(vals)
            move.post()
            check._add_operation('debited', move)
                
    @api.multi
    def returned(self,check, date):
        self.ensure_one()
        if check.state in ['holding'] or check.state in ['handed']:
            vals = check.get_bank_vals(
                'return_check', check.journal_id, date)
            move = self.env['account.move'].create(vals)
            move.post()            
            check._add_operation('returned', move)
            
            
    @api.multi
    def revert_return(self,check, date):
        self.ensure_one()
        if check.state in ['returned']:
            vals = check.get_bank_vals(
                'revert_return', check.journal_id, date)
            move = self.env['account.move'].create(vals)
            move.post()            
            check._add_operation('holding', move)
            
    @api.multi
    def bank_deposited(self, check, journal_id, date):
        self.ensure_one()
        if check.state in ['holding']:
            vals = check.get_bank_vals(
                'bank_deposited', journal_id, date)
            move = self.env['account.move'].create(vals)
            move.post()
            check._add_operation('deposited', move)
            
            
    @api.multi
    def claim(self, check, date):
        self.ensure_one()
        if check.state in ['rejected', 'returned'] and check.type == 'third_check':    
            operation = check._get_operation('holding', True)
            return check.action_create_debit_note(
            'reclaimed', 'customer', check.partner_id)
            #check._add_operation('claim', move)
            
            
    @api.multi
    def bank_rejected(self, check, date):
        self.ensure_one()
        if check.state in ['deposited']:
            operation = check._get_operation('deposited')
            journal_id = operation.origin.journal_id
            vals = check.get_bank_vals(
                'bank_reject', journal_id, date)
            move = self.env['account.move'].create(vals)
            move.post()
            check._add_operation('rejected', move)
