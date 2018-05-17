# -*- coding: utf-8 -*-
from odoo import fields, models
# from odoo.exceptions import UserError


class AccountConfigSettings(models.TransientModel):
    _inherit = 'account.config.settings'

    double_validation = fields.Boolean(
        related='company_id.double_validation'
    )
