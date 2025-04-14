##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api


class ChoosePaymentMethod(models.TransientModel):
    _name = 'choose.payment.method'
    _description = 'Choose payment method Wizard'

    order_id = fields.Many2one('sale.order', required=True, ondelete="cascade")
    journal_id = fields.Many2one('account.journal', string='Diario', required=True)
    available_payment_method_line_ids = fields.Many2many('account.payment.method.line',
                                                         compute='_compute_payment_method_line_fields')
    payment_method_line_id = fields.Many2one('account.payment.method.line', domain="[('id', 'in', available_payment_method_line_ids)]", string='Método de pago', required=True)

    available_installment_ids = fields.Many2many('account.card.installment',
                                                compute='_compute_installment_ids')

    installment_id = fields.Many2one('account.card.installment', domain="[('id', 'in', available_installment_ids)]", string='Cuota', required=True)
    amount_surcharge = fields.Float(
        string="Recargo financiero",
        compute='_compute_amount'
    )
    total_amount = fields.Float(
        string="Total a pagar",
        compute='_compute_amount'
    )

    @api.depends('installment_id')
    def _compute_amount(self):
        for rec in self:
            amount = rec.order_id.amount_total
            installment = rec.installment_id.financial_surcharge
            amount_surcharge = amount * installment
            rec.amount_surcharge = amount_surcharge
            rec.total_amount = amount + amount_surcharge

    @api.depends('payment_method_line_id')
    def _compute_installment_ids(self):
        for rec in self:
            payment_method_line_id = rec.payment_method_line_id
            payment_id = rec.journal_id.inbound_payment_method_line_ids.filtered(lambda tx: tx.payment_method_id.id == payment_method_line_id.id)
            rec.available_installment_ids = payment_id.available_card_ids.mapped('installment_ids').ids

    @api.depends('journal_id')
    def _compute_payment_method_line_fields(self):
        for rec in self:
            rec.available_payment_method_line_ids = rec.journal_id.inbound_payment_method_line_ids.mapped('payment_method_id').ids

    def button_confirm(self):
        for rec in self:
            product_id = self.env['product.product'].search([('is_financial_charge', '=', True)], limit=1)
            vals = {
                'product_id': product_id.id,
                'product_uom_qty': 1,
                'price_unit': rec.amount_surcharge,
                'order_id': rec.order_id.id,
            }
            self.env['sale.order.line'].create(vals)