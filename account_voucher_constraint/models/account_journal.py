# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields
import logging
_logger = logging.getLogger(__name__)


class account_journal(models.Model):
    _inherit = "account.journal"

    voucher_amount_restriction = fields.Selection([
        ('cant_be_cero', "Can't be 0"),
        ('must_be_cero', 'Must Be 0')],
        'Voucher Amount Restriction',
        # default='cant_be_cero',
        )
