# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from .. import utils

class account_withholding_automatic_wizard(models.TransientModel):
    _name = 'account.withholding.automatic.wizard'

    @api.model
    def get_tax_withholding_id(self):
        return self.tax_withholding_id.browse(self._context.get('active_id'))

    tax_withholding_id = fields.Many2one(
        'account.tax',
        'Withholding Tax',
        required=True,
        default=get_tax_withholding_id,
        ondelete='cascade',
    )

    account_id = fields.Char('Accounts', help='Can be used "AAA:ZZZ" or "AAA,BBB,CCC" or "AAA:CCC,DDD" or "AAA:CCC,DDD,!EEE"')
    city = fields.Char('City')
    state_id  = fields.Many2one('res.country.state','State')
    percent  = fields.Float('Percentage',digits=(1, 4),help='Ingresar entre 0-1 ')
    fix_amount  = fields.Float('Fix Amount')
    action_type = fields.Char('Action type passed on the context', required=True)

    def build_domain_fr_wizard(self):
        domain = []
        if self.account_id:
            domain = utils.translate_domain(self.account_id,"accounts")
        if self.city:
            domain = domain + utils.translate_domain(self.city,"city")
        if self.state_id:
            domain = domain + utils.translate_domain(self.state_id.name,"state_id")

        return domain

    @api.one
    def set_domains_in_original(self):
        if self.action_type == 'insert_domain1':
            self.tax_withholding_id.withholding_rule_ids.create({
                'tax_withholding_id': self.tax_withholding_id.id,
                'domain': self.build_domain_fr_wizard(),
                'percentage': self.percent,
                'fix_amount': self.fix_amount,
            })
        
        if self.action_type == 'insert_domain2':
            self.tax_withholding_id.withholding_user_error_domain = self.build_domain_fr_wizard()