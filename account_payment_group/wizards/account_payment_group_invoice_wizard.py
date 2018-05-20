##############################################################################
# For copyright and license notices, see __manifest__.py file in root directory
##############################################################################
from odoo import api, fields, models, _
from openerp.exceptions import ValidationError


class AccountPaymentGroupInvoiceWizard(models.TransientModel):
    _name = "account.payment.group.invoice.wizard"

    @api.model
    def default_payment_group(self):
        return self.env['account.payment.group'].browse(
            self._context.get('active_id', False))

    payment_group_id = fields.Many2one(
        'account.payment.group',
        default=default_payment_group,
        ondelete='cascade',
        required=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        'Journal',
        required=True,
        ondelete='cascade',
    )
    date_invoice = fields.Date(
        string='Refund Date',
        default=fields.Date.context_today,
        required=True
    )
    currency_id = fields.Many2one(
        related='payment_group_id.currency_id',
        readonly=True,
    )
    date = fields.Date(
        string='Accounting Date'
    )
    product_id = fields.Many2one(
        'product.product',
        required=True,
        domain=[('sale_ok', '=', True)],
    )
    tax_ids = fields.Many2many(
        'account.tax',
        string='Taxes',
    )
    amount_untaxed = fields.Monetary(
        string='Untaxed Amount',
        required=True,
        compute='_compute_amount_untaxed',
        inverse='_inverse_amount_untaxed',
    )
    # we make amount total the main one and the other computed because the
    # normal case of use would be to know the total amount and also this amount
    # is the suggested one on creating the wizard
    amount_total = fields.Monetary(
        string='Total Amount',
        required=True
    )
    description = fields.Char(
        string='Reason',
    )
    company_id = fields.Many2one(
        related='payment_group_id.company_id',
        readonly=True,
    )
    account_analytic_id = fields.Many2one(
        'account.analytic.account',
        'Analytic Account',
    )

    @api.onchange('product_id')
    def change_product(self):
        self.ensure_one()
        if self.payment_group_id.partner_type == 'purchase':
            taxes = self.product_id.supplier_taxes_id
        else:
            taxes = self.product_id.taxes_id
        company = self.company_id or self.env.user.company_id
        taxes = taxes.filtered(lambda r: r.company_id == company)
        self.tax_ids = self.payment_group_id.partner_id.with_context(
            force_company=company.id).property_account_position_id.map_tax(
                taxes)

    @api.onchange('amount_untaxed', 'tax_ids')
    def _inverse_amount_untaxed(self):
        self.ensure_one()
        if self.tax_ids:
            taxes = self.tax_ids.compute_all(
                self.amount_untaxed, self.company_id.currency_id, 1.0,
                product=self.product_id,
                partner=self.payment_group_id.partner_id)
            self.amount_total = taxes['total_included']
        else:
            self.amount_total = self.amount_untaxed

    @api.depends('tax_ids', 'amount_total')
    def _compute_amount_untaxed(self):
        """
        For now we implement inverse only for percent taxes. We could extend to
        other by simulating tax.price_include = True, computing tax and
        then restoring tax.price_include = False.
        """
        self.ensure_one()
        if any(x.amount_type != 'percent' for x in self.tax_ids):
            raise ValidationError(_(
                'You can only set amount total if taxes are of type '
                'percentage'))
        tax_percent = sum(
            [x.amount for x in self.tax_ids if not x.price_include])
        total_percent = (1 + tax_percent / 100) or 1.0
        self.amount_untaxed = self.amount_total / total_percent

    @api.onchange('payment_group_id')
    def change_payment_group(self):
        journal_type = 'sale'
        type_tax_use = 'sale'
        if self.payment_group_id.partner_type == 'purchase':
            journal_type = 'purchase'
            type_tax_use = 'purchase'
        journal_domain = [
            ('type', '=', journal_type),
            ('company_id', '=', self.payment_group_id.company_id.id),
        ]
        tax_domain = [
            ('type_tax_use', '=', type_tax_use),
            ('company_id', '=', self.payment_group_id.company_id.id)]
        self.journal_id = self.env['account.journal'].search(
            journal_domain, limit=1)
        # usually debit/credit note will be for the payment difference
        self.amount_total = abs(self.payment_group_id.payment_difference)
        return {'domain': {
            'journal_id': journal_domain,
            'tax_ids': tax_domain,
        }}

    @api.multi
    def get_invoice_vals(self):
        self.ensure_one()
        payment_group = self.payment_group_id
        if payment_group.partner_type == 'supplier':
            invoice_type = 'in_'
        else:
            invoice_type = 'out_'

        if self._context.get('refund'):
            invoice_type += 'refund'
        else:
            invoice_type += 'invoice'

        return {
            'name': self.description,
            'date': self.date,
            'date_invoice': self.date_invoice,
            'origin': _('Payment id %s') % payment_group.id,
            'journal_id': self.journal_id.id,
            'user_id': payment_group.partner_id.user_id.id,
            'partner_id': payment_group.partner_id.id,
            'type': invoice_type,
            # 'invoice_line_ids': [('invoice_type')],
        }

    @api.multi
    def confirm(self):
        self.ensure_one()

        invoice = self.env['account.invoice'].create(self.get_invoice_vals())

        inv_line_vals = {
            'product_id': self.product_id.id,
            'price_unit': self.amount_untaxed,
            'invoice_id': invoice.id,
            'invoice_line_tax_ids': [(6, 0, self.tax_ids.ids)],
        }
        invoice_line = self.env['account.invoice.line'].new(inv_line_vals)
        invoice_line._onchange_product_id()
        # restore chosen taxes (changed by _onchange_product_id)
        invoice_line.invoice_line_tax_ids = self.tax_ids
        line_values = invoice_line._convert_to_write(invoice_line._cache)
        line_values['price_unit'] = self.amount_untaxed
        if self.account_analytic_id:
            line_values['account_analytic_id'] = self.account_analytic_id.id
        invoice.write({'invoice_line_ids': [(0, 0, line_values)]})
        invoice.compute_taxes()
        invoice.action_invoice_open()

        # TODO this FIX is to be removed on v11. This is to fix reconcilation
        # of the invoice with secondary_currency and the debit note without
        # secondary_currency
        secondary_currency = self.payment_group_id.to_pay_move_line_ids.mapped(
            'currency_id')
        if len(secondary_currency) == 1:
            move_lines = invoice.move_id.line_ids.filtered(
                lambda x: x.account_id == invoice.account_id)
            # use _write because move is already posted
            if not move_lines.mapped('currency_id'):
                move_lines._write({
                    'currency_id': secondary_currency.id,
                    'amount_currency': 0.0,
                })

        self.payment_group_id.to_pay_move_line_ids += (
            invoice.open_move_line_ids)
