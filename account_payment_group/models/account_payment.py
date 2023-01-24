# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import logging
_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    payment_group_id = fields.Many2one(
        'account.payment.group',
        'Payment Group',
        readonly=True,
    )
    amount_company_currency = fields.Monetary(
        string='Amount on Company Currency',
        compute='_compute_amount_company_currency',
        inverse='_inverse_amount_company_currency',
        currency_field='company_currency_id',
    )
    other_currency = fields.Boolean(
        compute='_compute_other_currency',
    )
    force_amount_company_currency = fields.Monetary(
        string='Forced Amount on Company Currency',
        currency_field='company_currency_id',
        copy=False,
    )
    exchange_rate = fields.Float(
        string='Exchange Rate',
        compute='_compute_exchange_rate',
        # readonly=False,
        # inverse='_inverse_exchange_rate',
        digits=(16, 4),
    )
    l10n_ar_amount_company_currency_signed = fields.Monetary(
        currency_field='company_currency_id', compute='_compute_l10n_ar_amount_company_currency_signed')
    # campo a ser extendido y mostrar un nombre detemrinado en las lineas de
    # pago de un payment group o donde se desee (por ej. con cheque, retención,
    # etc)
    payment_method_description = fields.Char(
        compute='_compute_payment_method_description',
        string='Payment Method Desc.',
    )
    available_journal_ids = fields.Many2many(
        comodel_name='account.journal',
        compute='_compute_available_journal_ids'
    )

    label_journal_id = fields.Char(
        compute='_compute_label'
    )

    label_destination_journal_id = fields.Char(
        compute='_compute_label'
    )

    @api.depends('payment_type', 'payment_group_id')
    def _compute_available_journal_ids(self):
        """
        Este metodo odoo lo agrega en v16
        Igualmente nosotros lo modificamos acá para que funcione con esta logica:
        a) desde transferencias permitir elegir cualquier diario ya que no se selecciona compañía
        b) desde grupos de pagos solo permitir elegir diarios de la misma compañía
        NOTA: como ademas estamos mandando en el contexto del company_id, tal vez podriamos evitar pisar este metodo
        y ande bien en v16 para que las lineas de pago de un payment group usen la compañia correspondiente, pero
        lo que faltaria es hacer posible en las transferencias seleccionar una compañia distinta a la por defecto
        """
        journals = self.env['account.journal'].search([
            ('company_id', 'in', self.env.companies.ids), ('type', 'in', ('bank', 'cash'))
        ])
        for pay in self:
            filtered_domain = [('inbound_payment_method_line_ids', '!=', False)] if \
                pay.payment_type == 'inbound' else [('outbound_payment_method_line_ids', '!=', False)]
            if pay.payment_group_id:
                filtered_domain.append(('company_id', '=', pay.payment_group_id.company_id.id))
            pay.available_journal_ids = journals.filtered_domain(filtered_domain)

    @api.depends('payment_method_id')
    def _compute_payment_method_description(self):
        for rec in self:
            rec.payment_method_description = rec.payment_method_id.display_name

    @api.depends('amount_company_currency', 'payment_type')
    def _compute_l10n_ar_amount_company_currency_signed(self):
        """ new field similar to amount_company_currency_signed but:
        1. is positive for payments to suppliers
        2. we use the new field amount_company_currency instead of amount_total_signed, because amount_total_signed is
        computed only after saving
        We use l10n_ar prefix because this is a pseudo backport of future l10n_ar_withholding module """
        for payment in self:
            if payment.payment_type == 'outbound' and payment.partner_type == 'customer' or \
                    payment.payment_type == 'inbound' and payment.partner_type == 'supplier':
                payment.l10n_ar_amount_company_currency_signed = -payment.amount_company_currency
            else:
                payment.l10n_ar_amount_company_currency_signed = payment.amount_company_currency

    @api.depends('currency_id')
    def _compute_other_currency(self):
        for rec in self:
            rec.other_currency = False
            if rec.company_currency_id and rec.currency_id and \
               rec.company_currency_id != rec.currency_id:
                rec.other_currency = True

    @api.onchange('payment_group_id')
    def onchange_payment_group_id(self):
        # now we change this according when use save & new the context from the payment was erased and we need to use some data.
        # this change is due this odoo change https://github.com/odoo/odoo/commit/c14b17c4855fd296fd804a45eab02b6d3566bb7a
        if self.payment_group_id:
            self.date = self.payment_group_id.payment_date
            self.partner_type = self.payment_group_id.partner_type
            self.partner_id = self.payment_group_id.partner_id
            self.payment_type = 'inbound' if self.payment_group_id.partner_type  == 'customer' else 'outbound'
            self.amount = self.payment_group_id.payment_difference

    @api.depends('amount', 'other_currency', 'amount_company_currency')
    def _compute_exchange_rate(self):
        for rec in self:
            if rec.other_currency:
                rec.exchange_rate = rec.amount and (
                    rec.amount_company_currency / rec.amount) or 0.0
            else:
                rec.exchange_rate = False

    # this onchange is necesary because odoo, sometimes, re-compute
    # and overwrites amount_company_currency. That happends due to an issue
    # with rounding of amount field (amount field is not change but due to
    # rouding odoo believes amount has changed)
    @api.onchange('amount_company_currency')
    def _inverse_amount_company_currency(self):
        for rec in self:
            if rec.other_currency and rec.amount_company_currency != \
                    rec.currency_id._convert(
                        rec.amount, rec.company_id.currency_id,
                        rec.company_id, rec.date):
                force_amount_company_currency = rec.amount_company_currency
            else:
                force_amount_company_currency = False
            rec.force_amount_company_currency = force_amount_company_currency

    @api.depends('amount', 'other_currency', 'force_amount_company_currency')
    def _compute_amount_company_currency(self):
        """
        * Si las monedas son iguales devuelve 1
        * si no, si hay force_amount_company_currency, devuelve ese valor
        * sino, devuelve el amount convertido a la moneda de la cia
        """
        for rec in self:
            if not rec.other_currency:
                amount_company_currency = rec.amount
            elif rec.force_amount_company_currency:
                amount_company_currency = rec.force_amount_company_currency
            else:
                amount_company_currency = rec.currency_id._convert(
                    rec.amount, rec.company_id.currency_id,
                    rec.company_id, rec.date)
            rec.amount_company_currency = amount_company_currency

    @api.model_create_multi
    def create(self, vals_list):
        """ If a payment is created from anywhere else we create the payment group in top """
        recs = super().create(vals_list)
        for rec in recs.filtered(lambda x: not x.payment_group_id and not x.is_internal_transfer).with_context(
                created_automatically=True):
            if not rec.partner_id:
                raise ValidationError(_(
                    'Manual payments should not be created manually but created from Customer Receipts / Supplier Payments menus'))
            rec.payment_group_id = self.env['account.payment.group'].create({
                'company_id': rec.company_id.id,
                'partner_type': rec.partner_type,
                'partner_id': rec.partner_id.id,
                'payment_date': rec.date,
                'communication': rec.ref,
            })
            rec.payment_group_id.post()
        return recs

    @api.depends('payment_group_id')
    def _compute_destination_account_id(self):
        """
        If we are paying a payment gorup with paylines, we use account
        of lines that are going to be paid
        """
        for rec in self:
            to_pay_account = rec.payment_group_id.to_pay_move_line_ids.mapped(
                'account_id')
            if len(to_pay_account) > 1:
                raise ValidationError(_(
                    'To Pay Lines must be of the same account!'))
            elif len(to_pay_account) == 1:
                rec.destination_account_id = to_pay_account[0]
            else:
                super(AccountPayment, rec)._compute_destination_account_id()

    def show_details(self):
        """
        Metodo para mostrar form editable de payment, principalmente para ser
        usado cuando hacemos ajustes y el payment group esta confirmado pero
        queremos editar una linea
        """
        return {
            'name': _('Payment Lines'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.payment',
            'target': 'new',
            'res_id': self.id,
            'context': self._context,
        }

    def button_open_payment_group(self):
        self.ensure_one()
        return self.payment_group_id.get_formview_action()

    def _prepare_move_line_default_vals(self, write_off_line_vals=None):
        res = super()._prepare_move_line_default_vals(write_off_line_vals=write_off_line_vals)
        if self.force_amount_company_currency:
            difference = self.force_amount_company_currency - res[0]['credit'] - res[0]['debit']
            if res[0]['credit']:
                liquidity_field = 'credit'
                counterpart_field = 'debit'
            else:
                liquidity_field = 'debit'
                counterpart_field = 'credit'
            res[0].update({
                liquidity_field: self.force_amount_company_currency,
            })
            res[1].update({
                counterpart_field: res[1][counterpart_field] + difference,
            })
        return res

    @api.model
    def _get_trigger_fields_to_sincronize(self):
        res = super()._get_trigger_fields_to_sincronize()
        return res + ('force_amount_company_currency',)

    @api.depends_context('default_is_internal_transfer')
    def _compute_is_internal_transfer(self):
        """ Este campo se recomputa cada vez que cambia un diario y queda en False porque el segundo diario no va a
        estar completado. Como nosotros tenemos un menú especifico para poder registrar las transferencias internas,
        entonces si estamos en este menu siempre es transferencia interna"""
        if self._context.get('default_is_internal_transfer'):
            self.is_internal_transfer = True
        else:
            return super()._compute_is_internal_transfer()

    def _create_paired_internal_transfer_payment(self):
        for rec in self:
            super(AccountPayment, rec.with_context(
                default_force_amount_company_currency=rec.force_amount_company_currency
            ))._create_paired_internal_transfer_payment()

    @api.onchange("payment_type")
    def _compute_label(self):
        for rec in self:
            if rec.payment_type == "outbound":
                rec.label_journal_id = "Diario de origen"
                rec.label_destination_journal_id = "Diario de destino"
            else:
                rec.label_journal_id = "Diario de destino"
                rec.label_destination_journal_id = "Diario de origen"
