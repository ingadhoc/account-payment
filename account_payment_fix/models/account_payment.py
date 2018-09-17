from odoo import fields, models, api
# from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)


class AccountPaymentMethod(models.Model):
    _inherit = "account.payment.method"

    name = fields.Char(translate=True)


class AccountPayment(models.Model):
    _name = "account.payment"
    _inherit = ['mail.thread', 'account.payment']

    state = fields.Selection(track_visibility='always')
    amount = fields.Monetary(track_visibility='always')
    partner_id = fields.Many2one(track_visibility='always')
    journal_id = fields.Many2one(track_visibility='always')
    destination_journal_id = fields.Many2one(track_visibility='always')
    currency_id = fields.Many2one(track_visibility='always')
    # campo a ser extendido y mostrar un nombre detemrinado en las lineas de
    # pago de un payment group o donde se desee (por ej. con cheque, retención,
    # etc)
    payment_method_description = fields.Char(
        compute='_compute_payment_method_description',
        string='Payment Method',
    )

    @api.multi
    def _compute_payment_method_description(self):
        for rec in self:
            rec.payment_method_description = rec.payment_method_id.display_name

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
                ('id', '!=', rec.journal_id.id),
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
        # Al final dejamos que para transferencias se pueda elegir
        # cualquier sin importar si tiene outbound o no
        # else:
        elif self.payment_type == 'outbound':
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
            else:
                self.partner_type = False
            # limpiamos journal ya que podria no estar disponible para la nueva
            # operacion y ademas para que se limpien los payment methods
            self.journal_id = False
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

    def _onchange_amount(self):
        """
        Anulamos este onchange que termina cambiando el domain de journals
        y no es compatible con multicia y se pierde al guardar.
        TODO: ver que odoo con este onchange llama a
        _compute_journal_domain_and_types quien devolveria un journal generico
        cuando el importe sea cero, imagino que para hacer ajustes por
        diferencias de cambio
        """
        return True

    @api.onchange('journal_id')
    def _onchange_journal(self):
        """
        Sobre escribimos y desactivamos la parte del dominio de la funcion
        original ya que se pierde si se vuelve a entrar
        TODO: ver que odoo con este onchange llama a
        _compute_journal_domain_and_types quien devolveria un journal generico
        cuando el importe sea cero, imagino que para hacer ajustes por
        diferencias de cambio
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
            # si es una transferencia y no hay payment method de origen,
            # forzamos manual
            if not payment_methods and self.payment_type == 'transfer':
                payment_methods = self.env.ref(
                    'account.account_payment_method_manual_out')
            self.payment_method_id = (
                payment_methods and payment_methods[0] or False)
            # si se eligió de origen el mismo diario de destino, lo resetiamos
            if self.journal_id == self.destination_journal_id:
                self.destination_journal_id = False
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

    @api.model
    def get_amls(self):
        """ Review parameters of process_reconciliation() method and transform
        them to amls recordset. this one is return to recompute the payment
        values

        context keys(
            'counterpart_aml_dicts', 'new_aml_dicts', 'payment_aml_rec')

        :return: account move line recorset
        """
        counterpart_aml_data = self._context.get('counterpart_aml_dicts', [])
        new_aml_data = self._context.get('new_aml_dicts', [])

        counterpart_aml = self.env['account.move.line']
        if counterpart_aml_data:
            for item in counterpart_aml_data:
                counterpart_aml |= item.get(
                    'move_line', self.env['account.move.line'])

        new_aml = self.env['account.move.line']
        if new_aml_data:
            for aml_values in new_aml_data:
                new_aml = new_aml | new_aml.new(aml_values)

        return counterpart_aml, new_aml

    @api.model
    def fix_payment_info(self, values):
        """ Conciliation wiget infer some data to create the payment.
        This method improve the way tha info is compute and update
        (partner_type, partner_id, account_id) when needed

        1. If not partner given will try to find the partner from the related
        account move lines.

        2. If trying to validate one one line will set the accoun_id taking
        into acocunt the partner type supplier/customer payable/receivable
        respectively.

        3. payment_type will not be computed by the amount sign, will be
        compute from the related account type.

        If we can infer or fix any of the missing/wrong parameter will return
        a dictionary with the fixed values: posible keys

                (partner_id, partner_type, payment_type)

        If not will return an empty dictionary.

        return dictionary
        """
        res = {}

        counterpart_aml, new_aml = self.get_amls()

        if not any([counterpart_aml, new_aml]):
            return res

        # por mas que el usuario no haya selecccionado partner, si esta
        # pagando deuda usamos el partner de esa deuda
        partner_id = values.get('partner_id', False)
        if counterpart_aml and not partner_id and \
           len(counterpart_aml.mapped('partner_id')) == 1:
            partner_id = counterpart_aml.mapped('partner_id').id
            res.update({'partner_id': partner_id})

        # corregir la cuenta a usar, si estoy validando una linea sola. si soy
        # partner proveedor usar cuenta de proveedores del partner (pagable).
        # si soy partner cliente usar cuenta deudora por venta (a cobrar)
        if new_aml and partner_id:
            self.fix_widget_account(res)
            if 'account_id' in res:
                new_aml.account_id = res.get('account_id')

        # odoo manda partner type segun si el pago es positivo o no,
        # nosotros mejoramos infiriendo a partir de que tipo de deuda se
        # esta pagando
        partner_type = False
        amls = counterpart_aml | new_aml
        internal_type = amls.mapped('account_id.internal_type')
        if len(internal_type) == 1:
            if internal_type == ['payable']:
                partner_type = 'supplier'
            elif internal_type == ['receivable']:
                partner_type = 'customer'
            if partner_type:
                res.update({'partner_type': partner_type})
        return res

    @api.model
    def create(self, values):
        values.update(self.fix_payment_info(values))
        return super(AccountPayment, self).create(values)
