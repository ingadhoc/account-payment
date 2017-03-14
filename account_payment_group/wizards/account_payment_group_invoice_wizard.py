# -*- encoding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in root directory
##############################################################################
from openerp import api, fields, models, _


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
    amount = fields.Monetary(
        required=True
    )
    description = fields.Char(
        string='Reason',
    )

    @api.onchange('payment_group_id')
    def change_payment_group(self):
        journal_type = 'sale'
        if self.payment_group_id.partner_type == 'purchase':
            journal_type = 'purchase'
        journal_domain = [
            ('type', '=', journal_type),
            ('company_id', '=', self.payment_group_id.company_id.id),
        ]
        self.journal_id = self.env['account.journal'].search(
            journal_domain, limit=1)
        return {'domain': {'journal_id': journal_domain}}

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
            'price_unit': self.amount,
            'invoice_id': invoice.id,
        }

        invoice_line = self.env['account.invoice.line'].new(inv_line_vals)
        invoice_line._onchange_product_id()
        line_values = invoice_line._convert_to_write(invoice_line._cache)
        line_values['price_unit'] = self.amount
        invoice.write({'invoice_line_ids': [(0, 0, line_values)]})
        invoice.compute_taxes()
        invoice.signal_workflow('invoice_open')
        self.payment_group_id.to_pay_move_line_ids += (
            invoice.open_move_line_ids)
