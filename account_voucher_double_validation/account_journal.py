# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields


class AccountJournal(models.Model):

    _inherit = "account.journal"

    allow_validation_difference = fields.Boolean(
        help='If you are using double confirmation, you can allow some '
        'journals to be validate with difference to confirmation amount'
    )
