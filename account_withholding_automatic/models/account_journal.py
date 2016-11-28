# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields


class AccountJournal(models.Model):

    _inherit = "account.journal"

    automatic_withholdings = fields.Boolean(
        help='Make withholdings automatically on payments vouchers'
        ' confirmation'
    )
