# -*- coding: utf-8 -*-
from openerp import models, fields, api
import openerp.addons.decimal_precision as dp
from dateutil.relativedelta import relativedelta
import datetime


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
             ' enter withholding number when registering one.'
        # 'default_prefix': 'x-', 'default_padding': 8}",
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
    # calculation fields
    non_taxable_minimum = fields.Float(
        'Non-taxable Minimum',
        digits=dp.get_precision('Account'),
        )
    base_amount_type = fields.Selection([
        ('untaxed_amount', 'Untaxed Amount'),
        ('total_amount', 'Total Amount'),
        # neto gravado + no gravado / neto gravado / importe total
        # importe de iva?
        ],
        'Base Amount',
        help='Base amount used to get withholding amount',
        )
    accumulated_payments = fields.Selection([
        ('month', 'Month'),
        ('year', 'Year'),
        ],
        string='Accumulated Payments',
        help='If none is selected, then payments are not accumulated',
        )
    # TODO implement
    # allow_modification = fields.Boolean(
    #     )
    type = fields.Selection([
        ('none', 'None'),
        ('percentage', 'Percentage'),
        # ('fixed', 'Fixed Amount'),
        # ('code', 'Python Code'), ('balance', 'Balance')
         ],
        'Type',
        required=True,
        default='none',
        help="The computation method for the tax amount."
        )
    amount = fields.Float(
        'Amount',
        digits=dp.get_precision('Account'),
        help="For taxes of type percentage, enter % ratio between 0-1."
        )
    automatic_method = fields.Selection(
        [],
        string='Automatic Method',
        )

    @api.model
    def create(self, vals):
        if not vals.get('sequence_id'):
            # if we have the right to create a journal, we should be able to
            # create it's sequence.
            vals.update({'sequence_id': self.sudo().create_sequence(vals).id})
        return super(AccountTaxWithholding, self).create(vals)

    @api.multi
    def create_voucher_withholdings(self, voucher):
        # for tax in self.filtered(lambda x: x.type == 'percentage'):
        for tax in self.filtered(lambda x: x.type != 'none'):
            voucher_withholding = self.env[
                'account.voucher.withholding'].search([
                    ('voucher_id', '=', voucher.id),
                    ('tax_withholding_id', '=', tax.id),
                    ('automatic', '=', True),
                    ], limit=1)
            vals = tax.get_withholding_vals(voucher)
            if not vals.get('amount'):
                continue
            # vals = {
            #     # 'amount': voucher.amount * tax.amount,
            #     'voucher_id': voucher.id,
            #     'tax_withholding_id': tax.id,
            #     'automatic': True,
            #         }
            if voucher_withholding:
                voucher_withholding.write(vals)
            else:
                voucher_withholding = voucher_withholding.create(vals)
            # voucher_withholding.get_withholding_data()
        return True

    @api.model
    def create_sequence(self, vals):
        """ Create new no_gap entry sequence for every new tax withholding
        """
        seq = {
            'name': vals['name'],
            'implementation': 'no_gap',
            # 'prefix': prefix + "/%(year)s/",
            'padding': 8,
            'number_increment': 1
        }
        if 'company_id' in vals:
            seq['company_id'] = vals['company_id']
        return self.sequence_id.create(seq)

    @api.multi
    def get_non_taxable_minimum(self, voucher):
        self.ensure_one()
        return self.non_taxable_minimum

    @api.multi
    def get_withholdable_invoiced_amount(self, voucher):
        self.ensure_one()
        amount = 0.0
        for line in self.env['account.voucher.line'].search([
                ('voucher_id', '=', voucher.id)]):
            factor = self.get_withholdable_factor(line)
            sign = 1.0
            if voucher.type == 'payment':
                sign = -1.0
            if line.type == 'dr':
                sign = sign * -1.0
            amount += line.amount * sign * factor
        return amount

    @api.multi
    def get_withholdable_factor(self, voucher_line):
        self.ensure_one()
        factor = 1.0
        if self.base_amount_type == 'untaxed_amount':
            invoice = voucher_line.move_line_id.invoice
            factor = invoice.amount_untaxed / invoice.amount_total
        return factor

    # @api.multi
    # def get_period_withholding_amount(self, base_amount, voucher):
    #     self.ensure_one()
    #     if self.type == 'percentage':
    #         return base_amount * self.amount
    #     return False

    # @api.depends('tax_withholding_id', 'voucher_id')
    # def get_withholding_data(self):
    @api.multi
    def get_withholding_vals(self, voucher):
        self.ensure_one()
        # voucher = self.voucher_id
        withholdable_invoiced_amount = self.get_withholdable_invoiced_amount(
            voucher)
        withholdable_advanced_amount = voucher.writeoff_amount

        to_date = fields.Date.from_string(
            voucher.date) or datetime.date.today()
        accumulated_amount = previous_withholding_amount = 0.0
        accumulated_payments = self.accumulated_payments
        if accumulated_payments == 'month':
            previos_vouchers_domain = [
                ('partner_id', '=', voucher.partner_id.id),
                ('state', '=', 'posted'),
                ('id', '!=', voucher.id),
                ]
            if accumulated_payments == 'month':
                from_relative_delta = relativedelta(day=1)
            elif accumulated_payments == 'year':
                from_relative_delta = relativedelta(day=1, month=1)
            from_date = to_date + from_relative_delta
            previos_vouchers_domain += [
                ('date', '<=', to_date),
                ('date', '>=', from_date),
                ]
            same_period_vouchers = voucher.search(previos_vouchers_domain)
            accumulated_amount = sum(same_period_vouchers.mapped('amount'))
            previous_withholding_amount = sum(
                self.env['account.voucher.withholding'].search([
                    ('voucher_id', 'in', same_period_vouchers.ids),
                    ('tax_withholding_id', '=', self.id),
                    ]).mapped('amount'))

        total_amount = (
            accumulated_amount +
            withholdable_advanced_amount +
            withholdable_invoiced_amount)
        non_taxable_minimum = self.get_non_taxable_minimum(voucher)
        withholdable_base_amount = total_amount - non_taxable_minimum
        period_withholding_amount = withholdable_base_amount * self.amount
        # period_withholding_amount = self.get_period_withholding_amount(
        #     withholdable_base_amount, voucher)
        suggested_withholding_amount = (
            period_withholding_amount - previous_withholding_amount)

        return {
            'withholdable_invoiced_amount': withholdable_invoiced_amount,
            'accumulated_amount': accumulated_amount,
            'total_amount': total_amount,
            'non_taxable_minimum': non_taxable_minimum,
            'withholdable_base_amount': withholdable_base_amount,
            'period_withholding_amount': period_withholding_amount,
            'previous_withholding_amount': previous_withholding_amount,
            'suggested_withholding_amount': suggested_withholding_amount,
            'amount': suggested_withholding_amount,
            'voucher_id': voucher.id,
            'tax_withholding_id': self.id,
            'automatic': True,
        }
        # self.withholdable_invoiced_amount = withholdable_invoiced_amount
        # self.accumulated_amount = accumulated_amount
        # self.total_amount = total_amount
        # self.non_taxable_minimum = non_taxable_minimum
        # self.withholdable_base_amount = withholdable_base_amount
        # self.period_withholding_amount = period_withholding_amount
        # # TODO, que este valor lo devuelva el tax
        # self.previous_withholding_amount = previous_withholding_amount
        # self.suggested_withholding_amount
        # self.amount = suggested_withholding_amount


class account_chart_template(models.Model):
    _inherit = "account.chart.template"

    withholding_template_ids = fields.One2many(
        'account.tax.withholding.template',
        'chart_template_id',
        'Withholding Template List',
        help='List of all the withholding that have to be installed by the wizard'
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
