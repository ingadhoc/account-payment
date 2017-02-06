
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


from odoo import fields, models


class AccountConfigSettings(models.TransientModel):
    _inherit = 'account.config.settings'
    
    rejected_check_account_id = fields.Boolean(related='company_id.rejected_check_account_id')
    deferred_check_account_id = fields.Boolean(related='company_id.deferred_check_account_id')
    holding_check_account_id = fields.Boolean(related='company_id.holding_check_account_id')

    
    
