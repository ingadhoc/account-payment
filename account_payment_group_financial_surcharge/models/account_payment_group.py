##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api
from odoo.exceptions import UserError

class AccountPaymentGroup(models.Model):

    _inherit = "account.payment.group"

    financing_surcharge = fields.Monetary(compute='_computed_financing_surcharge')

    @api.depends('payment_ids.net_amount')
    def _computed_financing_surcharge(self):
        for rec in self:
            rec.financing_surcharge = sum(
                rec.payment_ids.filtered('financing_plan_id').mapped(lambda x: x.amount - x.net_amount))

    def post(self):
        if self.payment_ids.mapped('financing_plan_id'):
            product = self.company_id.product_surcharge_id
            if not product:
                raise UserError(
                    "To validate payment with finacing plan is necessary to have a product surcharge in the "
                    "company of the payment. Please check this in the Account Config")
            journal = self.env['account.journal'].search([
                ('type', '=', 'sale'),
                ('company_id', '=', self.company_id.id)], limit=1)
            taxes = product.taxes_id.filtered(lambda t: t.company_id.id == self.company_id.id)
            wiz = self.env['account.payment.group.invoice.wizard'].with_context(
                active_id=self.id, internal_type='debit_note').create({
                    'journal_id': journal.id,
                    'product_id': product.id,
                    'tax_ids': [(6, 0, taxes.ids)],
                    'amount_total': taxes.with_context(
                        force_price_include=True).compute_all(
                        self.financing_surcharge, currency=self.currency_id)['total_excluded'],
                })
            wiz.change_payment_group()
            wiz.confirm()
        super().post()
