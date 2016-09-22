# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, api, _
from openerp.exceptions import Warning
import logging
_logger = logging.getLogger(__name__)


class account_voucher(models.Model):
    _inherit = "account.voucher"

    @api.multi
    @api.constrains('state', 'journal_id', 'amount')
    def check_journal_amount_restriction(self):
        for voucher in self.filtered(lambda x: x.state == 'posted'):
            journal = self.journal_id
            if (
                    journal.voucher_amount_restriction == 'cant_be_cero' and
                    not voucher.amount
                    ):
                raise Warning(_(
                    "On Journal '%s' amount can't be cero!\n"
                    "* Voucher id: %i") % (journal.name, voucher.id))
            elif (
                    journal.voucher_amount_restriction == 'must_be_cero' and
                    voucher.amount
                    ):
                raise Warning(_(
                    "On Journal '%s' amount must be cero!\n"
                    "* Voucher id: %i") % (journal.name, voucher.id))
        return True
