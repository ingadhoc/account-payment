# -*- coding: utf-8 -*-
from openerp import models, fields
import logging
_logger = logging.getLogger(__name__)


class AccountConfigSsettings(models.TransientModel):
    _inherit = 'account.config.settings'

    group_choose_payment_type = fields.Boolean(
        'Choose Payment Type on Payments',
        help='Used if you want let user choose payment type (inbound or '
        'outbound) when registering a payment from a payment group',
        implied_group='account_payment_group.group_choose_payment_type',
    )
    group_pay_now_customer_invoices = fields.Boolean(
        'Allow pay now on customer invoices?',
        help='Allow users to choose a payment journal on invoices so that '
        'invoice is automatically paid after invoice validation. A payment '
        'will be created using choosen journal',
        implied_group='account_payment_group.group_pay_now_customer_invoices',
    )
    group_pay_now_vendor_invoices = fields.Boolean(
        'Allow pay now on vendor invoices?',
        help='Allow users to choose a payment journal on invoices so that '
        'invoice is automatically paid after invoice validation. A payment '
        'will be created using choosen journal',
        implied_group='account_payment_group.group_pay_now_vendor_invoices',
    )
