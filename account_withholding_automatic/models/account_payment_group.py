##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, api, fields, _
from odoo.exceptions import ValidationError


class AccountPaymentGroup(models.Model):

    _inherit = "account.payment.group"

    withholdings_amount = fields.Monetary(
        compute='_compute_withholdings_amount'
    )
    withholdable_advanced_amount = fields.Monetary(
        'Adjustment / Advance (untaxed)',
        help='Sometimes used for withholdings calculation',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )

    @api.onchange('unreconciled_amount')
    def set_withholdable_advanced_amount(self):
        for rec in self:
            rec.withholdable_advanced_amount = rec.unreconciled_amount

    @api.multi
    @api.depends(
        'payment_ids.tax_withholding_id',
        'payment_ids.amount',
    )
    def _compute_withholdings_amount(self):
        for rec in self:
            rec.withholdings_amount = sum(
                rec.payment_ids.filtered(
                    lambda x: x.tax_withholding_id).mapped('amount'))

    @api.multi
    def compute_withholdings(self):
        for rec in self:
            if rec.partner_type != 'supplier':
                continue
            # limpiamos el type por si se paga desde factura ya que el en ese
            # caso viene in_invoice o out_invoice y en search de tax filtrar
            # por impuestos de venta y compra (y no los nuestros de pagos
            # y cobros)
            self.env['account.tax'].with_context(type=None).search([
                ('type_tax_use', '=', rec.partner_type),
                ('company_id', '=', rec.company_id.id),
            ]).create_payment_withholdings(rec)

    @api.multi
    def confirm(self):
        res = super(AccountPaymentGroup, self).confirm()
        for rec in self:
            if rec.company_id.automatic_withholdings:
                rec.compute_withholdings()
        return res

    def _get_withholdable_amounts(
            self, withholding_amount_type, withholding_advances):
        """ Method to help on getting withholding amounts from account.tax
        TODO when payment is validated we should get amounts from matched
        amounts and not from selected debt
        """
        self.ensure_one()
        if withholding_amount_type == 'untaxed_amount':
            withholdable_invoiced_amount = self.selected_debt_untaxed
        else:
            withholdable_invoiced_amount = self.selected_debt
        withholdable_advanced_amount = 0.0
        # if the unreconciled_amount is negative, then the user wants to make
        # a partial payment. To get the right untaxed amount we need to know
        # which invoice is going to be paid, we only allow partial payment
        # on last invoice
        if self.withholdable_advanced_amount < 0.0 and \
                self.to_pay_move_line_ids:
            withholdable_advanced_amount = 0.0

            sign = self.partner_type == 'supplier' and -1.0 or 1.0
            sorted_to_pay_lines = sorted(
                self.to_pay_move_line_ids,
                key=lambda a: a.date_maturity or a.date)

            # last line to be reconciled
            partial_line = sorted_to_pay_lines[-1]
            if sign * partial_line.amount_residual < \
                    sign * self.withholdable_advanced_amount:
                raise ValidationError(_(
                    'Seleccionó deuda por %s pero aparentente desea pagar '
                    ' %s. En la deuda seleccionada hay algunos comprobantes de'
                    ' mas que no van a poder ser pagados (%s). Deberá quitar '
                    ' dichos comprobantes de la deuda seleccionada para poder '
                    'hacer el correcto cálculo de las retenciones.' % (
                        self.selected_debt,
                        self.to_pay_amount,
                        partial_line.move_id.display_name,
                        )))

            if withholding_amount_type == 'untaxed_amount' and \
                    partial_line.invoice_id:
                invoice_factor = partial_line.invoice_id._get_tax_factor()
            else:
                invoice_factor = 1.0

            # le descontamos de la base imponible el saldo que no se esta
            # pagando descontado de iva
            withholdable_invoiced_amount -= (
                sign * self.withholdable_advanced_amount
                * invoice_factor)
        elif withholding_advances:
            withholdable_advanced_amount = \
                self.withholdable_advanced_amount
        return (withholdable_advanced_amount, withholdable_invoiced_amount)
