# -*- coding: utf-8 -*-
# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, api


class AccountPayment(models.Model):
    _inherit = "account.payment"

    @api.multi
    def cancel(self):
        for rec in self:
            if rec.payment_type == 'transfer':
                transfer_account = rec.company_id.transfer_account_id
                rec.move_line_ids.filtered(
                    lambda x: x.account_id == transfer_account
                ).remove_move_reconcile()
        return super(AccountPayment, self).cancel()
