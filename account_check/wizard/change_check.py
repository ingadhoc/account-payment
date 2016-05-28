# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields, api


class account_change_check(models.TransientModel):
    _name = 'account.change.check'

    @api.model
    def get_original_check(self):
        return self.original_check_id.browse(self._context.get('active_id'))

    original_check_id = fields.Many2one(
        'account.check',
        'Original Check',
        required=True,
        default=get_original_check,
        ondelete='cascade',
    )
    journal_id = fields.Many2one(
        related='original_check_id.journal_id',
    )
    type = fields.Selection(
        related='original_check_id.type',
    )
    number = fields.Integer(
        'Number',
        required=True,
    )
    issue_date = fields.Date(
        'Issue Date',
        required=True,
        default=fields.Date.context_today,
    )
    payment_date = fields.Date(
        'Payment Date',
        help="Only if this check is post dated",
    )

    # issue checks
    checkbook_id = fields.Many2one(
        'account.checkbook',
        'Checkbook',
        ondelete='cascade',
    )
    issue_check_subtype = fields.Selection(
        related='checkbook_id.issue_check_subtype',
    )

    # third checks
    bank_id = fields.Many2one(
        'res.bank', 'Bank',
    )
    vat = fields.Char(
        # TODO rename to Owner VAT
        'Owner Vat',
    )
    owner_name = fields.Char(
        'Owner Name',
    )

    @api.onchange('original_check_id')
    def change_original_check(self):
        self.checkbook_id = self.original_check_id.checkbook_id
        self.vat = self.original_check_id.vat
        self.owner_name = self.original_check_id.owner_name
        self.bank_id = self.original_check_id.bank_id

    @api.multi
    def confirm(self):
        self.ensure_one()
        vals = {
            'vat': self.vat,
            'owner_name': self.owner_name,
            'checkbook_id': self.checkbook_id.id,
            'payment_date': self.payment_date,
            'issue_date': self.issue_date,
            'number': self.number,
        }
        new_check = self.original_check_id.copy(vals)
        self.original_check_id.write({
            'replacing_check_id': new_check.id,
            'amount': 0.0,
            'company_currency_amount': 0.0,
        })
        self.original_check_id.signal_workflow('change_check')
        new_check.signal_workflow('draft_router')
        return new_check
