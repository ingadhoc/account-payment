##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models, api, _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    rejected_check_account_id = fields.Many2one(
        'account.account',
        'Rejected Checks Account',
        help='Rejection Checks account, for eg. "Rejected Checks"',
    )
    deferred_check_account_id = fields.Many2one(
        'account.account',
        'Deferred Checks Account',
        help='Deferred Checks account, for eg. "Deferred Checks"',
    )
    holding_check_account_id = fields.Many2one(
        'account.account',
        'Holding Checks Account',
        help='Holding Checks account for third checks, '
        'for eg. "Holding Checks"',
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
            ) % (type, self.name))
        return account
