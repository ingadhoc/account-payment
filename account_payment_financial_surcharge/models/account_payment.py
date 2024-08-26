##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountPayment(models.Model):

    _inherit = "account.payment"

    financing_surcharge = fields.Monetary(
        compute='_computed_financing_surcharge'
    )
    available_card_ids = fields.Many2many(
        'account.card',
        string='Cards',
        related='payment_method_line_id.available_card_ids'
    )
    card_id = fields.Many2one(
        'account.card',
        string='Card',
        compute='_compute_financing_plan', store=True, readonly=False
    )
    installment_id = fields.Many2one(
        'account.card.installment',
        string='Installment plan',
        compute='_compute_installment',
        store=True, readonly=False,
    )
    net_amount = fields.Monetary(
        compute='_computed_net_amount',
        inverse='_inverse_net_amount'
    )

    @api.depends('available_card_ids', 'payment_type')
    def _compute_financing_plan(self):
        for rec in self:
            if rec.card_id not in rec.available_card_ids:
                # reset card in case avaiable cards change (payment method change)
                self.card_id = False

    @api.depends('card_id.installment_ids')
    def _compute_installment(self):
        if len(self.card_id.installment_ids.ids) > 0:
            self.installment_id = self.card_id.installment_ids.ids[0]
        else:
            self.installment_id = False

    @api.depends('amount')
    def _computed_net_amount(self):
        for rec in self:
            rec.net_amount = rec.amount / (rec.installment_id.surcharge_coefficient or 1)

    @api.onchange('installment_id')
    def _onchange_instalment(self):
        """ no agregamos este onchange en el de _inverse_net_amount porque si no el amount se inicializa en cero.
        Eventualmente habria que mejorar esto. Se podria tal vez pasar el default por vista al net_amount tmb """
        for rec in self:
            rec._inverse_net_amount()

    @api.onchange('net_amount')
    def _inverse_net_amount(self):
        for rec in self:
            rec.with_context(skip_account_move_synchronization=True).amount = rec.net_amount * (rec.installment_id.surcharge_coefficient or 1)

    @api.model
    def default_get(self, default_fields):
        if self._context.get('open_invoice_payment', False):
            self = self.with_context(active_ids=None, active_model=None)
        return super().default_get(default_fields)

    @api.depends('net_amount')
    def _computed_financing_surcharge(self):
        for rec in self:
            rec.financing_surcharge = rec.amount - rec.net_amount

    def action_post(self):
        """ If we have a financial surcharge in the payments we need to auto create a debit note with the surcharge """
        for rec in self.filtered(lambda p: p.financing_surcharge > 0):
            product = rec.company_id.product_surcharge_id
            if not product:
                raise UserError(
                    "To validate payment with financing plan is necessary to have a product surcharge in the "
                    "company of the payment. Please check this in the Account Config")
            # Obtengo las notas de debito relacionadas con el grupo de pago.
            # y computo la suma del precio toal del producto de surchage y si es menor al residual de las notas de debito
            # lo seteo como monto a facturar restandolo de el recargo caculado (esperado) 
            related_debit_note = rec.to_pay_move_line_ids.mapped('move_id').filtered(lambda x: x.l10n_latam_document_type_id.internal_type == 'debit_note')
            surchage_products_total = sum(related_debit_note.mapped('line_ids').filtered(lambda x:  x.product_id == product).mapped('price_total'))
            financing_surcharge_to_invoice = rec.financing_surcharge - (min(surchage_products_total, sum(related_debit_note.mapped('amount_residual'))))
            if financing_surcharge_to_invoice > 0:                    
                taxes = product.taxes_id.filtered(lambda t: t.company_id.id == rec.company_id.id)
                journal = self.env['account.journal'].search([('type', '=', 'sale'), ('company_id', '=', rec.company_id.id)], limit=1)
                wiz = self.env['account.payment.invoice.wizard'].with_context(
                    is_automatic_subcharge=True, active_id=rec.id, internal_type='debit_note').create({
                        'journal_id': journal.id,
                        'product_id': product.id,
                        'tax_ids': [(6, 0, taxes.ids)],
                        'amount_total': self.financing_surcharge,
                    })
                wiz._onchange_journal_id()
                wiz.change_payment_group()
                wiz.amount_total = rec.financing_surcharge
                wiz.confirm()

                # If we are registering a payment of a draft invoice then we need to remove the invoice from the debts of the payment
                # in order to be able to post/reconcile the payment (this is needed because in odoo 17 we are not able to reconcile
                # draft account.move. only can reconcile posted ones)
                if self.env.context.get('open_invoice_payment'):
                    move_line_ids = self._context.get('to_pay_move_line_ids')
                    move_lines = move_line_ids and self.env['account.move.line'].browse(move_line_ids) or self.env['account.move.line']
                    if not move_lines:
                        move_lines = rec.to_pay_move_line_ids
                    draft_invoices = move_lines and move_lines.mapped('move_id').filtered(lambda x: x.state == 'draft')
                    if draft_invoices:
                        # remove draft invoice from debt
                        rec.to_pay_move_line_ids -= rec.to_pay_move_line_ids.filtered(lambda aml: aml.move_id in draft_invoices)

        return super().action_post()
