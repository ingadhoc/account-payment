# -*- coding: utf-8 -*-
from openerp import models, fields, api, _
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    check_deposit_id = fields.Many2one(
        'account.check.deposit',
        string='Check Deposit',
        copy=False
    )
    check_type = fields.Selection(
        [('issue_check', 'Issue Check'), ('third_check', 'Third Check')],
    )
    check_payment_date = fields.Date(
        related='date_maturity'
    )
    check_issue_date = fields.Date(
        'Issue Date',
        # required=True,
        # readonly=True,
        # states={'draft': [('readonly', False)]},
        default=fields.Date.context_today,
    )
    check_state = fields.Selection([
        ('draft', 'Draft'),
        ('holding', 'Holding'),
        ('deposited', 'Deposited'),
        ('handed', 'Handed'),
        ('rejected', 'Rejected'),
        ('debited', 'Debited'),
        ('returned', 'Returned'),
        ('changed', 'Changed'),
        ('cancel', 'Cancel'),
    ],
        'Check State',
        # required=True,
        # track_visibility='onchange',
        default='draft',
        compute='_compute_check_state'
        # copy=False,
    )
    checkbook_id = fields.Many2one(
        'account.checkbook',
        'Checkbook',
        # readonly=True,
        # states={'draft': [('readonly', False)]},
        # TODO hacer con un onchange
        # default=_get_checkbook,
    )

    @api.one
    def _compute_check_state(self):
        state = False
        # if self.payment_method_code == 'received_third_check':
        #     if self.state == 'draft':
        #         state = 'draft'
        #     elif self.state == 'posted':
        #         state = 'holding'
        self.check_state = state
    check_bank_id = fields.Many2one(
        'res.bank', 'Bank',
        # readonly=True,
        # states={'draft': [('readonly', False)]}
    )
    # currency_id = fields.Many2one(
    #     'res.currency',
    #     string='Currency',
    #     readonly=True,
    #     related='voucher_id.journal_id.currency',
    # )
    check_owner_vat = fields.Char(
        # TODO rename to Owner VAT
        'Owner Vat',
        # readonly=True,
        # states={'draft': [('readonly', False)]}
    )
    check_owner_name = fields.Char(
        'Owner Name',
        # readonly=True,
        # states={'draft': [('readonly', False)]}
    )
