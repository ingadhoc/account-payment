# -*- coding: utf-8 -*-
from openerp import models, fields


class account_journal(models.Model):
    _inherit = "account.journal"

    double_validation = fields.Boolean(
        'Double Validation?',
        help='Use two steps validation on payments to suppliers of this '
        'journal?',
        )
