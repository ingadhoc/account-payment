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
        if self.payment_ids.mapped('installment_id'):
            product = self.company_id.product_surcharge_id
            if not product:
                raise UserError(
                    "To validate payment with finacing plan is necessary to have a product surcharge in the "
                    "company of the payment. Please check this in the Account Config")

            move_line_ids = self._context.get('to_pay_move_line_ids', False)
            move_lines = move_line_ids and self.env['account.move.line'].browse(move_line_ids) or self.env['account.move.line']
            taxes = product.taxes_id.filtered(lambda t: t.company_id.id == self.company_id.id)
            draft_invoices = move_lines and move_lines.mapped('move_id').filtered(lambda x: x.state == 'draft')
            if draft_invoices:
                amount_total = taxes.filtered(lambda x: not x.price_include).with_context(force_price_include=True).compute_all(
                    self.financing_surcharge, currency=self.currency_id)['total_excluded']
                draft_invoices[0].write({'invoice_line_ids': [(0, 0, {
                    'product_id': product.id,
                    'price_unit': amount_total,
                    'tax_ids': [(6, 0, taxes.ids)],
                })]})
            else:
                journal = self.env['account.journal'].search([('type', '=', 'sale'), ('company_id', '=', self.company_id.id)], limit=1)
                wiz = self.env['account.payment.group.invoice.wizard'].with_context(
                    active_id=self.id, internal_type='debit_note').create({
                        'journal_id': journal.id,
                        'product_id': product.id,
                        'tax_ids': [(6, 0, taxes.ids)],
                        'amount_total': self.financing_surcharge,
                    })
                refund = self.env['account.move'].with_context(internal_type='debit_note').new({
                    'move_type': wiz.get_invoice_vals().get('move_type'),
                    'journal_id': journal.id,
                    'partner_id': self.partner_id.id,
                    'company_id': self.company_id.id,
                })
                wiz.journal_document_type_id = refund.l10n_latam_document_type_id
                wiz.change_payment_group()
                wiz.amount_total = self.financing_surcharge
                wiz.confirm()
            super().post()
            if draft_invoices:
                (self.payment_ids.mapped('move_line_ids') + draft_invoices[0].line_ids).filtered(
                    lambda line: not line.reconciled and line.account_id.internal_type in ('payable', 'receivable')).reconcile()
        else:
            super().post()

        return True
