# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import fields, models, api, _
from openerp.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    rejected_check_account_id = fields.Many2one(
        'account.account',
        'Rejected Check Account',
        # required=True,
        help='Rejection Checks account, for eg. "Rejected Checks"',
        # domain=[('type', 'in', ['other'])],
    )
    deferred_check_account_id = fields.Many2one(
        'account.account',
        'Deferred Check Account',
        # required=True,
        help='Deferred Checks account, for eg. "Deferred Checks"',
        # domain=[('type', 'in', ['other'])],
    )
    holding_check_account_id = fields.Many2one(
        'account.account',
        'Holding Check Account',
        # required=True,
        help='Holding Checks account for third checks, '
        'for eg. "Holding Checks"',
        # domain=[('type', 'in', ['other'])],
    )

    @api.multi
    def _get_check_account(self, type):
        self.ensure_one()
        if type == 'holding':
            account = self.holding_check_account_id
        elif type == 'rejected':
            account = self.rejected_check_account_id
        elif type == 'deferred':
            account = self.deferred_check_account_id
        else:
            raise UserError(_("Type %s not implemented!"))
        if not account:
            raise UserError(_(
                'No checks %s account defined for company %s'
            ) % self.name)
        return account
