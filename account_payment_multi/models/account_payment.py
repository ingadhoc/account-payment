# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, api, fields, _
from openerp.exceptions import UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    payment_multi_id = fields.Many2one(
        'account.payment.multi', 'Payment Multi')
