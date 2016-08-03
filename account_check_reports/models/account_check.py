# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, api, fields


class account_check_action(models.TransientModel):
    _inherit = "account.check.action"

    @api.model
    def _get_checks(self):
        check_ids = self.env['account.check'].browse(
            self._context.get('active_ids', []))
        if check_ids:
            return check_ids

    check_ids = fields.Many2many(
        'account.check',
        default=_get_checks)

    @api.multi
    def action_confirm(self):
        assert len(self) == 1
        super(account_check_action, self).action_confirm()
        return self.env['report'].get_action(
            self.check_ids, 'account_check_deposit_report')
