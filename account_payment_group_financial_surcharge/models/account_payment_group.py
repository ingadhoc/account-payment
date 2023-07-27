##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountPaymentGroup(models.Model):

    _inherit = "account.payment.group"

    financing_surcharge = fields.Monetary(
        compute='_computed_financing_surcharge')

    @api.depends('payment_ids.net_amount')
    def _computed_financing_surcharge(self):
        for rec in self:
            rec.financing_surcharge = sum(rec.payment_ids.filtered('installment_id').mapped(lambda x: x.amount - x.net_amount))

    def post(self):
        """ If we have a financial surcharge in the payments we need to auto create a debit note with the surcharge """
        if self.filtered(lambda p: p.financing_surcharge > 0):
            product = self.company_id.product_surcharge_id
            if not product:
                raise UserError(
                    "To validate payment with finacing plan is necessary to have a product surcharge in the "
                    "company of the payment. Please check this in the Account Config")
            ## Obtengo las notas de debito relacionadas con el grupo de pago.
            ## y computo la suma del precio toal del producto de surchage y si es menor al residual de las notas de debito
            ## lo seteo como monto a facturar restandolo de el recargo caculado (esperado) 
            related_debit_note = self.to_pay_move_line_ids.mapped('move_id').filtered(lambda x: x.l10n_latam_document_type_id.internal_type == 'debit_note')
            surchage_products_total =  sum(related_debit_note.mapped('line_ids').filtered(lambda x:  x.product_id == product).mapped('price_total'))
            financing_surcharge_to_invoice = self.financing_surcharge - (min(surchage_products_total, sum(related_debit_note.mapped('amount_residual'))))
            if financing_surcharge_to_invoice > 0:                    
                taxes = product.taxes_id.filtered(lambda t: t.company_id.id == self.company_id.id)
                journal = self.env['account.journal'].search([('type', '=', 'sale'), ('company_id', '=', self.company_id.id)], limit=1)
                wiz = self.env['account.payment.group.invoice.wizard'].with_context(
                    is_automatic_subcharge=True, active_id=self.id, internal_type='debit_note').create({
                        'journal_id': journal.id,
                        'product_id': product.id,
                        'tax_ids': [(6, 0, taxes.ids)],
                        'amount_total': financing_surcharge_to_invoice,
                    })
                wiz._onchange_journal_id()
                wiz.change_payment_group()
                wiz.amount_total = financing_surcharge_to_invoice
                wiz.confirm()

                # If we are registering a payment of a draft invoice then we need to remove the invoice from the debts of the payment group
                # in order to be able to post/reconcile the payment group (this is needed because in odoo 16 we are not able to renconcile
                # draft account.move. only can reconcile posted ones)
                if self.env.context.get('open_invoice_payment'):
                    move_line_ids = self._context.get('to_pay_move_line_ids')
                    move_lines = move_line_ids and self.env['account.move.line'].browse(move_line_ids) or self.env['account.move.line']
                    if not move_lines:
                        move_lines = self.to_pay_move_line_ids
                    draft_invoices = move_lines and move_lines.mapped('move_id').filtered(lambda x: x.state == 'draft')
                    if draft_invoices:
                        # remove draft invoice from debt
                        self.to_pay_move_line_ids -= self.to_pay_move_line_ids.filtered(lambda aml: aml.move_id in draft_invoices)

        return super().post()
