
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


from odoo import fields, models


class AccountConfigSettings(models.TransientModel):
    _inherit = 'account.config.settings'

    # Own

    own_check_rejected_account_id = fields.Many2one(related='company_id.own_check_rejected_account_id')
    own_check_cancelled_account_id = fields.Many2one(related='company_id.own_check_cancelled_account_id')
    deferred_check_account_id = fields.Many2one(related='company_id.deferred_check_account_id')
    payment_method_validate_jr = fields.Boolean(related='company_id.payment_method_validate_jr')

    # Third Party

    third_party_checks_cancelled_account_id = fields.Many2one(related='company_id.third_party_checks_cancelled_account_id')
    third_party_checks_bounced_endorsed_account_id = fields.Many2one(related='company_id.third_party_checks_bounced_endorsed_account_id')
    rejected_check_account_id = fields.Many2one(related='company_id.rejected_check_account_id')
    holding_check_account_id = fields.Many2one(related='company_id.holding_check_account_id')
