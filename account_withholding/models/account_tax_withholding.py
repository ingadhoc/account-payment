# -*- coding: utf-8 -*-
from openerp import models, fields, api
import openerp.addons.decimal_precision as dp
# from dateutil.relativedelta import relativedelta
# import datetime


class AccountTaxWithholding(models.Model):
    _name = "account.tax.withholding"
    _description = "Account Withholding Taxes"

    name = fields.Char(
        'Name',
        required=True,
    )
    description = fields.Char(
        'Description',
        required=True,
    )
    type_tax_use = fields.Selection(
        [('receipt', 'Receipt'), ('payment', 'Payment'), ('all', 'All')],
        'Tax Application',
        required=True
    )
    active = fields.Boolean(
        'Active',
        default=True,
        help="If the active field is set to False,"
             "it will allow you to hide the tax without removing it.")
    sequence_id = fields.Many2one(
        'ir.sequence',
        'Internal Number Sequence',
        domain=[('code', '=', 'account.tax.withholding')],
        context=(
            "{'default_code': 'account.tax.withholding',"
            " 'default_name': name}"),
        help='If no sequence provided then it will be required for you to'
             ' enter withholding number when registering one.',
        # 'default_prefix': 'x-', 'default_padding': 8}",
        copy=False
    )
    account_id = fields.Many2one(
        'account.account',
        'Account',
        required=True,
    )
    ref_account_id = fields.Many2one(
        'account.account',
        'Refund Account',
        required=True,
    )
    account_analytic_id = fields.Many2one(
        'account.analytic.account',
        'Analytic Account',
    )
    ref_account_analytic_id = fields.Many2one(
        'account.analytic.account',
        'Refund Analytic Account',
    )
    company_id = fields.Many2one(
        'res.company',
        'Company',
        required=True,
        default=lambda self: self.env['res.company']._company_default_get(
            'account.tax.withholding')
    )
    #
    # Fields used for the Tax declaration
    #
    # TODO ver si necesitamos los base o no
    base_code_id = fields.Many2one(
        'account.tax.code',
        'Base Code',
        help="Use this code for the tax declaration."
    )
    tax_code_id = fields.Many2one(
        'account.tax.code',
        'Tax Code',
        help="Use this code for the tax declaration.",
    )
    base_sign = fields.Float(
        'Base Code Sign',
        help="Usually 1 or -1.",
        digits=dp.get_precision('Account'),
        default=1,
    )
    tax_sign = fields.Float(
        'Tax Code Sign',
        help="Usually 1 or -1.",
        digits=dp.get_precision('Account'),
        default=1,
    )
    ref_base_code_id = fields.Many2one(
        'account.tax.code',
        'Refund Base Code',
        help="Use this code for the tax declaration."
    )
    ref_tax_code_id = fields.Many2one(
        'account.tax.code',
        'Refund Tax Code',
        help="Use this code for the tax declaration.",
    )
    ref_base_sign = fields.Float(
        'Refund Base Code Sign',
        help="Usually 1 or -1.",
        digits=dp.get_precision('Account'),
        default=1,
    )
    ref_tax_sign = fields.Float(
        'Refund Tax Code Sign',
        help="Usually 1 or -1.",
        digits=dp.get_precision('Account'),
        default=1,
    )

    @api.model
    def create(self, vals):
        if not vals.get('sequence_id'):
            # if we have the right to create a journal, we should be able to
            # create it's sequence.
            vals.update({'sequence_id': self.sudo().create_sequence(vals).id})
        return super(AccountTaxWithholding, self).create(vals)

    @api.model
    def create_sequence(self, vals):
        """ Create new no_gap entry sequence for every new tax withholding
        """
        seq = {
            'name': vals['name'],
            'implementation': 'no_gap',
            'code': 'account.tax.withholding',
            # 'prefix': prefix + "/%(year)s/",
            'padding': 8,
            'number_increment': 1
        }
        if 'company_id' in vals:
            seq['company_id'] = vals['company_id']
        return self.sequence_id.create(seq)


class account_chart_template(models.Model):
    _inherit = "account.chart.template"

    withholding_template_ids = fields.One2many(
        'account.tax.withholding.template',
        'chart_template_id',
        'Withholding Template List',
        help='List of all the withholding that have to be installed by the '
        'wizard'
    )


class account_tax_withholding_template(models.Model):
    _name = "account.tax.withholding.template"
    _inherit = "account.tax.withholding"
    _description = "Account Withholding Taxes Template"

    chart_template_id = fields.Many2one(
        'account.chart.template',
        'Chart Template',
        required=True
    )
    account_id = fields.Many2one(
        'account.account.template',
    )
    ref_account_id = fields.Many2one(
        'account.account.template',
    )
    base_code_id = fields.Many2one(
        'account.tax.code.template',
    )
    tax_code_id = fields.Many2one(
        'account.tax.code.template',
    )
    ref_base_code_id = fields.Many2one(
        'account.tax.code.template',
    )
    ref_tax_code_id = fields.Many2one(
        'account.tax.code.template',
    )

    @api.multi
    def _generate_withholding(
            self, tax_code_ref, account_ref, company_id):
        """
        This method generate taxes from templates.

        :param self: list of browse record of the tax templates to process
        :param tax_code_template_ref: Taxcode templates reference.
        :param company_id: id of the company the wizard is running for
        :returns:
            {
            'tax_template_to_tax': mapping between tax template and the newly generated taxes corresponding,
            'account_dict': dictionary containing a to-do list with all the accounts to assign on new taxes
            }
        """
        res = {}
        for tax in self:
            vals_tax = {
                'name': tax.name,
                'description': tax.description,
                'type_tax_use': tax.type_tax_use,
                'base_code_id': tax_code_ref.get(tax.base_code_id.id),
                'tax_code_id': tax_code_ref.get(tax.tax_code_id.id),
                'ref_base_code_id': tax_code_ref.get(tax.ref_base_code_id.id),
                'ref_tax_code_id': tax_code_ref.get(tax.ref_tax_code_id.id),
                'base_sign': tax.base_sign,
                'tax_sign': tax.tax_sign,
                'base_sign': tax.ref_base_sign,
                'tax_sign': tax.ref_tax_sign,
                'company_id': company_id,
                'account_id': account_ref.get(tax.account_id.id),
                'ref_account_id': account_ref.get(tax.ref_account_id.id),
            }
            new_tax = self.env['account.tax.withholding'].create(vals_tax)
            res[tax.id] = new_tax.id
        return res
