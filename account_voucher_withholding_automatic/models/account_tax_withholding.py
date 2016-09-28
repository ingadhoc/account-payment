# -*- coding: utf-8 -*-
from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import Warning
from ast import literal_eval
from openerp.tools.safe_eval import safe_eval as eval
# from openerp.addons.account.account import get_precision_tax
from dateutil.relativedelta import relativedelta
import datetime


class AccountTaxWithholding(models.Model):
    _inherit = "account.tax.withholding"
    _description = "Account Withholding Taxes"

    non_taxable_amount = fields.Float(
        'Non-taxable Amount',
        digits=dp.get_precision('Account'),
        help="Amount to be substracted before applying alicuot"
    )
    non_taxable_minimum = fields.Float(
        'Non-taxable Minimum',
        digits=dp.get_precision('Account'),
        help="Amounts lower than this wont't have any withholding"
    )
    base_amount_type = fields.Selection([
        ('untaxed_amount', 'Untaxed Amount'),
        ('total_amount', 'Total Amount'),
        # ('percentage_of_total', 'Percentage Of Total'),
        # neto gravado + no gravado / neto gravado / importe total
        # importe de iva?
    ],
        'Base Amount',
        help='Base amount used to get withholding amount',
    )
    # base_amount_percentage = fields.Float(
    #     'Percentage',
    #     digits=get_precision_tax(),
    #     help="Enter % ratio between 0-1.",
    #     default=1,
    # )
    user_error_message = fields.Char(
    )
    user_error_domain = fields.Char(
        default="[]",
        help='Write a domain over account voucher module'
    )
    advances_are_withholdable = fields.Boolean(
        'Advances are Withholdable?',
        default=True,
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
        # ('percentage', 'Percentage'),
        ('based_on_rule', 'Based On Rule'),
        # ('fixed', 'Fixed Amount'),
        ('code', 'Python Code'),
        # ('balance', 'Balance')
    ],
        'Type',
        required=True,
        default='none',
        help="The computation method for the tax amount."
    )
    python_compute = fields.Text(
        'Python Code',
        default='''
# withholdable_base_amount
# voucher: account.voucher object
# partner: res.partner object
# withholding_tax: account.tax.withholding object

result = withholdable_base_amount * 0.10
        ''',
    )
    rule_ids = fields.One2many(
        'account.tax.withholding.rule',
        'tax_withholding_id',
        'Rules',
    )
    # amount = fields.Float(
    #     'Amount',
    #     # digits=dp.get_precision('Account'),
    #     digits=get_precision_tax(),
    #     help="For taxes of type percentage, enter % ratio between 0-1."
    #     )

    @api.one
    @api.constrains('non_taxable_amount', 'non_taxable_minimum')
    def check_non_taxable_amounts(self):
        if self.non_taxable_amount > self.non_taxable_minimum:
            raise Warning(_(
                'Non-taxable Amount can not be greater than Non-taxable '
                'Minimum'))

    @api.multi
    def _get_rule(self, voucher):
        self.ensure_one()
        # do not return rule if other type
        if self.type != 'based_on_rule':
            return False
        for rule in self.rule_ids:
            try:
                domain = literal_eval(rule.domain)
            except Exception, e:
                raise Warning(_(
                    'Could not eval rule domain "%s".\n'
                    'This is what we get:\n%s' % (rule.domain, e)))
            domain.append(('id', '=', voucher.id))
            applies = voucher.search(domain)
            if applies:
                return rule
        return False

    @api.multi
    def create_voucher_withholdings(self, voucher):
        # for tax in self.filtered(lambda x: x.type == 'based_on_rule'):
        #     voucher.search([()])
        # for tax in self.filtered(lambda x: x.type == 'percentage'):
        for tax in self.filtered(lambda x: x.type != 'none'):
            voucher_withholding = self.env[
                'account.voucher.withholding'].search([
                    ('voucher_id', '=', voucher.id),
                    ('tax_withholding_id', '=', tax.id),
                    ('automatic', '=', True),
                ], limit=1)
            if tax.user_error_message and tax.user_error_domain:
                try:
                    domain = literal_eval(tax.user_error_domain)
                except Exception, e:
                    raise Warning(_(
                        'Could not eval rule domain "%s".\n'
                        'This is what we get:\n%s' % (
                            tax.user_error_domain, e)))
                domain.append(('id', '=', voucher.id))
                if voucher.search(domain):
                    raise Warning(tax.user_error_message)
            vals = tax.get_withholding_vals(voucher)
            if not vals.get('computed_withholding_amount'):
                # if on refresh no more withholding, we delete if it exists
                if voucher_withholding:
                    voucher_withholding.unlink()
                continue

            # we copy withholdable_base_amount on base_amount
            vals['base_amount'] = vals.get('withholdable_base_amount')
            vals['amount'] = vals.get('computed_withholding_amount')

            # por ahora no imprimimos el comment, podemos ver de llevarlo a
            # otro campo si es de utilidad
            vals.pop('comment')
            if voucher_withholding:
                voucher_withholding.write(vals)
            else:
                voucher_withholding = voucher_withholding.create(vals)
        return True

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
            factor = (invoice.amount_total and (
                invoice.amount_untaxed / invoice.amount_total) or 1.0)
        # elif self.base_amount_type == 'percentage_of_total':
        #     factor = self.base_amount_percentage
        return factor

    @api.multi
    def get_withholding_vals(self, voucher):
        self.ensure_one()
        # voucher = self.voucher_id
        withholdable_invoiced_amount = self.get_withholdable_invoiced_amount(
            voucher)
        withholdable_advanced_amount = 0.0
        if self.advances_are_withholdable:
            withholdable_advanced_amount = voucher.advance_amount

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
            for same_period_voucher in same_period_vouchers:
                # obtenemos importe acumulado sujeto a retencion de voucher
                # anteriores
                accumulated_amount += self.get_withholdable_invoiced_amount(
                    same_period_voucher)
                if self.advances_are_withholdable:
                    accumulated_amount += same_period_voucher.advance_amount
            # accumulated_amount = sum(same_period_vouchers.mapped('amount'))
            previous_withholding_amount = sum(
                self.env['account.voucher.withholding'].search([
                    ('voucher_id', 'in', same_period_vouchers.ids),
                    ('tax_withholding_id', '=', self.id),
                ]).mapped('amount'))

        total_amount = (
            accumulated_amount +
            withholdable_advanced_amount +
            withholdable_invoiced_amount)
        # non_taxable_minimum = self.get_non_taxable_minimum(voucher)
        non_taxable_minimum = self.non_taxable_minimum
        non_taxable_amount = self.non_taxable_amount
        withholdable_base_amount = ((total_amount > non_taxable_minimum) and (
            total_amount - non_taxable_amount) or 0.0)

        comment = False
        if self.type == 'code':
            localdict = {
                'withholdable_base_amount': withholdable_base_amount,
                'voucher': voucher,
                'partner': voucher.partner_id,
                'withholding_tax': self,
            }
            eval(self.python_compute, localdict, mode="exec", nocopy=True)
            period_withholding_amount = localdict['result']
        else:
            rule = self._get_rule(voucher)
            percentage = 0.0
            fix_amount = 0.0
            if rule:
                percentage = rule.percentage
                fix_amount = rule.fix_amount
                comment = '%s x %s + %s' % (
                    withholdable_base_amount,
                    percentage,
                    fix_amount)

            period_withholding_amount = (
                (total_amount > non_taxable_minimum) and (
                    withholdable_base_amount * percentage + fix_amount) or 0.0)

        # withholding can not be negative
        computed_withholding_amount = max(0, (
            period_withholding_amount - previous_withholding_amount))

        return {
            'withholdable_invoiced_amount': withholdable_invoiced_amount,
            'withholdable_advanced_amount': withholdable_advanced_amount,
            'accumulated_amount': accumulated_amount,
            'total_amount': total_amount,
            'non_taxable_minimum': non_taxable_minimum,
            'non_taxable_amount': non_taxable_amount,
            'withholdable_base_amount': withholdable_base_amount,
            'period_withholding_amount': period_withholding_amount,
            'previous_withholding_amount': previous_withholding_amount,
            'computed_withholding_amount': computed_withholding_amount,
            'base_amount': withholdable_base_amount,
            'voucher_id': voucher.id,
            'tax_withholding_id': self.id,
            'automatic': True,
            'comment': comment,
        }
