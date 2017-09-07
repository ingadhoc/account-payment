# -*- coding: utf-8 -*-
from openerp import fields, models, api
# from openerp.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # inicio backport commit d19cf48499b42fbd24e6a7ec283433a577362666
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('sent', 'Sent'),
        ('reconciled', 'Reconciled'),
        ('cancel', 'Cancelled')],
        readonly=True,
        default='draft',
        copy=False,
        string="Status",
    )

    # backport
    @api.multi
    def cancel(self):
        res = super(AccountPayment, self).cancel()
        self.write({'state': 'cancel'})
        return res

    @api.multi
    def action_draft(self):
        return self.write({'state': 'draft'})

    # fin backport

    # nuevo campo funcion para definir dominio de los metodos
    payment_method_ids = fields.Many2many(
        'account.payment.method',
        compute='_compute_payment_methods'
    )
    journal_ids = fields.Many2many(
        'account.journal',
        compute='_compute_journals'
    )
    # journal_at_least_type = fields.Char(
    #     compute='_compute_journal_at_least_type'
    # )
    destination_journal_ids = fields.Many2many(
        'account.journal',
        compute='_compute_destination_journals'
    )

    @api.multi
    def onchange(self, values, field_name, field_onchange):
        """
        Idea obtenida de aca
        https://github.com/odoo/odoo/issues/16072#issuecomment-289833419
        por el cambio que se introdujo en esa mimsa conversación, TODO en v11
        no haría mas falta, simplemente domain="[('id', 'in', x2m_field)]"
        Otras posibilidades que probamos pero no resultaron del todo fue:
        * agregar onchange sobre campos calculados y que devuelvan un dict con
        domain. El tema es que si se entra a un registro guardado el onchange
        no se ejecuta
        * usae el modulo de web_domain_field que esta en un pr a la oca
        """
        for field in field_onchange.keys():
            if field.startswith((
                    'payment_method_ids.',
                    'destination_journal_ids.', 'journal_ids.')):
                del field_onchange[field]
        return super(AccountPayment, self).onchange(
            values, field_name, field_onchange)

    @api.multi
    @api.depends(
        # 'payment_type',
        'journal_id',
    )
    def _compute_destination_journals(self):
        for rec in self:
            domain = [
                ('type', 'in', ('bank', 'cash')),
                # al final pensamos mejor no agregar esta restricción, por ej,
                # para poder transferir a tarjeta a pagar. Esto solo se usa
                # en transferencias
                # ('at_least_one_inbound', '=', True),
                ('company_id', '=', rec.journal_id.company_id.id),
            ]
            rec.destination_journal_ids = rec.journal_ids.search(domain)

    # @api.multi
    # @api.depends(
    #     'payment_type',
    # )
    # def _compute_journal_at_least_type(self):
    #     for rec in self:
    #         if rec.payment_type == 'inbound':
    #             journal_at_least_type = 'at_least_one_inbound'
    #         else:
    #             journal_at_least_type = 'at_least_one_outbound'
    #         rec.journal_at_least_type = journal_at_least_type

    @api.multi
    def get_journals_domain(self):
        """
        We get domain here so it can be inherited
        """
        self.ensure_one()
        domain = [('type', 'in', ('bank', 'cash'))]
        if self.payment_type == 'inbound':
            domain.append(('at_least_one_inbound', '=', True))
        else:
            domain.append(('at_least_one_outbound', '=', True))
        return domain

    @api.multi
    @api.depends(
        'payment_type',
    )
    def _compute_journals(self):
        for rec in self:
            rec.journal_ids = rec.journal_ids.search(rec.get_journals_domain())

    @api.multi
    @api.depends(
        'journal_id.outbound_payment_method_ids',
        'journal_id.inbound_payment_method_ids',
        'payment_type',
    )
    def _compute_payment_methods(self):
        for rec in self:
            if rec.payment_type in ('outbound', 'transfer'):
                methods = rec.journal_id.outbound_payment_method_ids
            else:
                methods = rec.journal_id.inbound_payment_method_ids
            rec.payment_method_ids = methods

    @api.onchange('payment_type')
    def _onchange_payment_type(self):
        """
        Sobre escribimos y desactivamos la parte del dominio de la funcion
        original ya que se pierde si se vuelve a entrar
        """
        if not self.invoice_ids:
            # Set default partner type for the payment type
            if self.payment_type == 'inbound':
                self.partner_type = 'customer'
            elif self.payment_type == 'outbound':
                self.partner_type = 'supplier'
        # # Set payment method domain
        # res = self._onchange_journal()
        # if not res.get('domain', {}):
        #     res['domain'] = {}
        # res['domain']['journal_id'] = self.payment_type == 'inbound' and [
        #     ('at_least_one_inbound', '=', True)] or [
        #     ('at_least_one_outbound', '=', True)]
        # res['domain']['journal_id'].append(('type', 'in', ('bank', 'cash')))
        # return res

    # @api.onchange('partner_type')
    def _onchange_partner_type(self):
        """
        Agregasmos dominio en vista ya que se pierde si se vuelve a entrar
        Anulamos funcion original porque no haria falta
        """
        return True

    @api.onchange('journal_id')
    def _onchange_journal(self):
        """
        Sobre escribimos y desactivamos la parte del dominio de la funcion
        original ya que se pierde si se vuelve a entrar
        """
        if self.journal_id:
            self.currency_id = (
                self.journal_id.currency_id or self.company_id.currency_id)
            # Set default payment method
            # (we consider the first to be the default one)
            payment_methods = (
                self.payment_type == 'inbound' and
                self.journal_id.inbound_payment_method_ids or
                self.journal_id.outbound_payment_method_ids)
            self.payment_method_id = (
                payment_methods and payment_methods[0] or False)
        #     # Set payment method domain
        #     # (restrict to methods enabled for the journal and to selected
        #     # payment type)
        #     payment_type = self.payment_type in (
        #         'outbound', 'transfer') and 'outbound' or 'inbound'
        #     return {
        #         'domain': {
        #             'payment_method_id': [
        #                 ('payment_type', '=', payment_type),
        #                 ('id', 'in', payment_methods.ids)]}}
        # return {}

    @api.multi
    @api.depends('invoice_ids', 'payment_type', 'partner_type', 'partner_id')
    def _compute_destination_account_id(self):
        """
        We send force_company on context so payments can be created from parent
        companies. We try to send force_company on self but it doesnt works, it
        only works sending it on partner
        """
        res = super(AccountPayment, self)._compute_destination_account_id()
        for rec in self.filtered(
                lambda x: not x.invoice_ids and x.payment_type != 'transfer'):
            partner = self.partner_id.with_context(
                force_company=self.company_id.id)
            if self.partner_type == 'customer':
                self.destination_account_id = (
                    partner.property_account_receivable_id.id)
            else:
                self.destination_account_id = (
                    partner.property_account_payable_id.id)
        return res
