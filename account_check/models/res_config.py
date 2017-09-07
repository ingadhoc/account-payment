# -*- coding: utf-8 -*-
from odoo import fields, models
# from odoo.exceptions import UserError


class AccountConfigSettings(models.TransientModel):
    _inherit = 'account.config.settings'

    rejected_check_account_id = fields.Many2one(
        related='company_id.rejected_check_account_id',
    )
    deferred_check_account_id = fields.Many2one(
        related='company_id.deferred_check_account_id',
    )
    holding_check_account_id = fields.Many2one(
        related='company_id.holding_check_account_id',
    )
