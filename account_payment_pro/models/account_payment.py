from odoo import models, fields, api, Command, _
from odoo.exceptions import ValidationError, UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # TODO. por ahora por simplicidad y para mantener lo que teniamos hasta 16 hacemos que todos los campos de deuda y demas
    # sean en moneda de la compañia (antes era en moneda del pay group que siempre era la moneda de la cia), currency_field='company_currency_id',
    # desde account_payment_group, modelo account.payment
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
        # digits=(16, 4),
    )
    # TODO deberiamos ver de borrar esto. el tema es que los campos nativos de odoo no refelajn importe en moenda de cia
    # hasta en tanto se guarde el payment (en parte porque vienen heredados desde el move)
    # no solo eso si no que tmb viene pisado en los payments y computa solo si hay liquidity lines pero no cuentas de
    # outstanding
    # TODO de hecho tenemos que analizar si queremos mantener todo lo de matched y demas en moneda de cia o moneda de
    # pago
    amount_company_currency_signed_pro = fields.Monetary(
        currency_field='company_currency_id', compute='_compute_amount_company_currency_signed_pro',)
    payment_total = fields.Monetary(
        compute='_compute_payment_total',
        string='Payment Total',
        tracking=True,
        currency_field='company_currency_id'
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

    # desde account_payment_group, modelo account.payment.group
    matched_amount = fields.Monetary(
        compute='_compute_matched_amounts',
        currency_field='company_currency_id',
    )
    unmatched_amount = fields.Monetary(
        compute='_compute_matched_amounts',
        currency_field='currency_id',
    )
    selected_debt = fields.Monetary(
        # string='To Pay lines Amount',
        string='Selected Debt',
        compute='_compute_selected_debt',
        currency_field='company_currency_id',
    )
    unreconciled_amount = fields.Monetary(
        string='Adjustment / Advance',
        currency_field='company_currency_id',
    )
    # reconciled_amount = fields.Monetary(compute='_compute_amounts')
    to_pay_amount = fields.Monetary(
        compute='_compute_to_pay_amount',
        inverse='_inverse_to_pay_amount',
        string='To Pay Amount',
        # string='Total To Pay Amount',
        readonly=True,
        tracking=True,
        currency_field='company_currency_id',
    )
    has_outstanding = fields.Boolean(
        compute='_compute_has_outstanding',
    )
    to_pay_move_line_ids = fields.Many2many(
        'account.move.line',
        'account_move_line_payment_to_pay_rel',
        'payment_id',
        'to_pay_line_id',
        string="To Pay Lines",
        compute='_compute_to_pay_move_lines', store=True,
        help='This lines are the ones the user has selected to be paid.',
        copy=False,
        readonly=False,
        check_company=True,
    )
    matched_move_line_ids = fields.Many2many(
        'account.move.line',
        compute='_compute_matched_move_line_ids',
        help='Lines that has been matched to payments, only available after '
        'payment validation',
    )
    payment_difference = fields.Monetary(
        compute='_compute_payment_difference',
        readonly=True,
        string="Payments Difference",
        currency_field='company_currency_id',
        help="Difference between selected debt (or to pay amount) and "
        "payments amount"
    )
    payment_difference_handling = fields.Selection(
        string="Payment Difference Handling",
        selection=[('open', 'Keep open'), ('reconcile', 'Mark as fully paid')],
        # compute='_compute_payment_difference_handling',
        # store=True,
        # readonly=False,
        default='open',
    )
    writeoff_account_id = fields.Many2one(
        comodel_name='account.account',
        string="Difference Account",
        copy=False,
        domain="[('deprecated', '=', False), ('account_type', 'in', ['expense', 'income', 'income_other'])]",
        check_company=True,
        # compute='_compute_writeoff_account_id',
        # store=True,
        # readonly=False,
    )
    writeoff_label = fields.Char(string='Journal Item Label', default='Write-Off',
                                 help='Change label of the counterpart that will hold the payment difference')
    is_approved = fields.Boolean(string="Approved", tracking=True, copy=False,)
    requiere_double_validation = fields.Boolean(compute='_compute_requiere_double_validation')

    def _check_to_pay_lines_account(self):
        """ TODO ver si esto tmb lo llevamos a la UI y lo mostramos como un warning.
        tmb podemos dar mas info al usuario en el error """
        for rec in self:
            accounts = rec.to_pay_move_line_ids.mapped('account_id')
            if len(accounts) > 1:
                raise ValidationError(_('To Pay Lines must be of the same account!'))

    def action_approve(self):
        # chequeamos lineas a pagar antes de confirmar pago para evitar idas y vueltas de validacion
        self._check_to_pay_lines_account()
        self.filtered(lambda x: x.state == 'draft').is_approved = True

    def action_unapprove(self):
        # chequeamos lineas a pagar antes de confirmar pago para evitar idas y vueltas de validacion
        self._check_to_pay_lines_account()
        self.filtered(lambda x: x.state == 'draft').is_approved = False

    def action_draft(self):
        self.is_approved = False
        super().action_draft()

    @api.model
    def _get_confimed_blocked_field(self):
        return ['partner_id', 'partner_type', 'to_pay_move_line_ids', 'unreconciled_amount',
                'withholdable_advanced_amount', 'company_id', 'to_pay_amount']

    def write(self, vals):
        if self.filtered('is_approved'):
            if set(vals) & set(self._get_confimed_blocked_field()):
                raise UserError(_('Your are trying to modify a protected field on an approved payment. Set it back to edit if you want to make this modification.'))
        return super().write(vals)

    @api.depends('company_id.double_validation', 'partner_type')
    def _compute_requiere_double_validation(self):
        double_validation = self.env['account.payment']
        if 'force_simple' not in self._context:
            double_validation = self.filtered(
                lambda x: not x.is_internal_transfer and x.company_id.double_validation and
                not x.is_approved and x.partner_type == 'supplier')
            double_validation.requiere_double_validation = True
        (self - double_validation).requiere_double_validation = False

    ##############################
    # desde modelo account.payment
    ##############################

    # TODO re-evaluar. tal vez mejor esto en un modulo multicompany?
    # @api.depends('payment_type')
    # def _compute_available_journal_ids(self):
    #     """
    #     Este metodo odoo lo agrega en v16
    #     Igualmente nosotros lo modificamos acá para que funcione con esta logica:
    #     a) desde transferencias permitir elegir cualquier diario ya que no se selecciona compañía
    #     b) desde grupos de pagos solo permitir elegir diarios de la misma compañía
    #     NOTA: como ademas estamos mandando en el contexto del company_id, tal vez podriamos evitar pisar este metodo
    #     y ande bien en v16 para que las lineas de pago de un payment group usen la compañia correspondiente, pero
    #     lo que faltaria es hacer posible en las transferencias seleccionar una compañia distinta a la por defecto
    #     """
    #     journals = self.env['account.journal'].search([
    #         ('company_id', 'in', self.env.companies.ids), ('type', 'in', ('bank', 'cash'))
    #     ])
    #     for pay in self:
    #         filtered_domain = [('inbound_payment_method_line_ids', '!=', False)] if \
    #             pay.payment_type == 'inbound' else [('outbound_payment_method_line_ids', '!=', False)]
    #         pay.available_journal_ids = journals.filtered_domain(filtered_domain)

    @api.depends('currency_id')
    def _compute_other_currency(self):
        for rec in self:
            rec.other_currency = False
            if rec.company_currency_id and rec.currency_id and \
               rec.company_currency_id != rec.currency_id:
                rec.other_currency = True

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

    @api.depends('to_pay_move_line_ids')
    def _compute_destination_account_id(self):
        """
        If we are paying a payment gorup with paylines, we use account
        of lines that are going to be paid
        """
        for rec in self:
            to_pay_account = rec.to_pay_move_line_ids.mapped('account_id')
            if to_pay_account:
                # tomamos la primer si hay mas de una, luego en el post si la deuda se intenta conciliar odoo
                # devuelve error. No lo protegemos acá por estas razones:
                # 1. el boton add all no se podria usar porque ya hace un write y el usuario deberia elegir a mano los apuntes
                # 2. le vamos a dar error al usuario en algunos casos sin que sea necesario ya que luego, si el importe es menor
                # no llega a intentar conciliarse con est epago
                rec.destination_account_id = to_pay_account[0]
            else:
                super(AccountPayment, rec)._compute_destination_account_id()

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        # TODO: elimino los write_off_line_vals  porque los regenero tanto aca
        # como en retenciones. esto puede generar problemas
        write_off_line_vals = []
        if self.payment_difference > 0 and self.payment_difference_handling == 'reconcile':
            if self.payment_type == 'inbound':
                # Receive money.
                write_off_amount_currency = self.payment_difference
            else:
                # Send money.
                write_off_amount_currency = -self.payment_difference

            write_off_line_vals.append({
                'name': self.writeoff_label,
                'account_id': self.writeoff_account_id.id,
                'partner_id': self.partner_id.id,
                'currency_id': self.currency_id.id,
                'amount_currency': write_off_amount_currency,
                'balance': self.currency_id._convert(write_off_amount_currency, self.company_id.currency_id,
                                                     self.company_id, self.date),
            })
        res = super()._prepare_move_line_default_vals(write_off_line_vals=write_off_line_vals, force_balance=force_balance)
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
    def _get_trigger_fields_to_synchronize(self):
        res = super()._get_trigger_fields_to_synchronize()
        # si bien es un metodo api.model usamos este hack para chequear si es la creacion de un payment que termina
        # triggereando un write y luego llamando a este metodo y dando error, por ahora no encontramos una mejor forma
        # esto esta ligado de alguna manera a un llamado que se hace dos veces por "culpa" del método
        # "_inverse_amount_company_currency". Si bien no es elegante para todas las pruebas que hicimos funcionó bien.
        if self.mapped('open_move_line_ids'):
            res = res + ('force_amount_company_currency',)
        return res + ('payment_difference_handling',)

    # TODO traer de account_ux y verificar si es necesario
    # @api.depends_context('default_is_internal_transfer')
    # def _compute_is_internal_transfer(self):
    #     """ Este campo se recomputa cada vez que cambia un diario y queda en False porque el segundo diario no va a
    #     estar completado. Como nosotros tenemos un menú especifico para poder registrar las transferencias internas,
    #     entonces si estamos en este menu siempre es transferencia interna"""
    #     if self._context.get('default_is_internal_transfer'):
    #         self.is_internal_transfer = True
    #     else:
    #         return super()._compute_is_internal_transfer()

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

    ####################################
    # desde modelo account.payment.group
    ####################################

    @api.depends('line_ids')
    def _compute_matched_move_line_ids(self):
        """
        Lar partial reconcile vinculan dos apuntes con credit_move_id y
        debit_move_id.
        Buscamos primeros todas las que tienen en credit_move_id algun apunte
        de los que se genero con un pago, etnonces la contrapartida
        (debit_move_id), son cosas que se pagaron con este pago. Repetimos
        al revz (debit_move_id vs credit_move_id)
        TODO v18, ver si podemos reutilizar reconciled_invoice_ids y/o reconciled_bill_ids
        al menos podremos re-usar codigo sql para optimizar performance
        Por ahora no lo estamos usando porque el actual código de odoo solo muestra facturas o algo así (por ej. si hay
        conciliacion de deuda de un asiento normal no lo muestra)
        """
        for rec in self:
            payment_lines = rec.line_ids.filtered(lambda x: x.account_type in self._get_valid_payment_account_types())
            debit_moves = payment_lines.mapped('matched_debit_ids.debit_move_id')
            credit_moves = payment_lines.mapped('matched_credit_ids.credit_move_id')
            debit_lines_sorted = debit_moves.filtered(lambda x: x.date_maturity != False).sorted(key=lambda x: (x.date_maturity, x.move_id.name))
            credit_lines_sorted = credit_moves.filtered(lambda x: x.date_maturity != False).sorted(key=lambda x: (x.date_maturity, x.move_id.name))
            debit_lines_without_date_maturity = debit_moves - debit_lines_sorted
            credit_lines_without_date_maturity = credit_moves - credit_lines_sorted
            rec.matched_move_line_ids = ((debit_lines_sorted + debit_lines_without_date_maturity) | (credit_lines_sorted + credit_lines_without_date_maturity)) - payment_lines

    @api.depends(
        'state',
        'amount_company_currency_signed_pro',
        )
    def _compute_matched_amounts(self):
        for rec in self:
            rec.matched_amount = 0.0
            rec.unmatched_amount = 0.0
            if rec.state != 'posted':
                continue
            # damos vuelta signo porque el payments_amount tmb lo da vuelta,
            # en realidad porque siempre es positivo y se define en funcion
            # a si es pago entrante o saliente
            sign = rec.partner_type == 'supplier' and -1.0 or 1.0
            rec.matched_amount = sign * sum(
                rec.matched_move_line_ids.with_context(matched_payment_ids=rec.ids).mapped('payment_matched_amount'))
            rec.unmatched_amount = rec.payment_total - rec.matched_amount

    @api.depends('to_pay_move_line_ids')
    def _compute_has_outstanding(self):
        for rec in self:
            rec.has_outstanding = False
            if rec.state != 'draft':
                continue
            if rec.partner_type == 'supplier':
                lines = rec.to_pay_move_line_ids.filtered(lambda x: x.amount_residual > 0.0)
            else:
                lines = rec.to_pay_move_line_ids.filtered(lambda x: x.amount_residual < 0.0)
            if len(lines) != 0:
                rec.has_outstanding = True

    @api.depends('amount_company_currency_signed_pro')
    def _compute_payment_total(self):
        for rec in self:
            rec.payment_total = rec.amount_company_currency_signed_pro

    @api.depends('amount_company_currency', 'payment_type')
    def _compute_amount_company_currency_signed_pro(self):
        """ new field similar to amount_company_currency_signed but:
        1. is positive for payments to suppliers
        2. we use the new field amount_company_currency instead of amount_total_signed, because amount_total_signed is
        computed only after saving
        We use l10n_ar prefix because this is a pseudo backport of future l10n_ar_withholding module """
        for payment in self:
            if payment.payment_type == 'outbound' and payment.partner_type == 'customer' or \
                    payment.payment_type == 'inbound' and payment.partner_type == 'supplier':
                payment.amount_company_currency_signed_pro = -payment.amount_company_currency
            else:
                payment.amount_company_currency_signed_pro = payment.amount_company_currency

    def _get_payment_difference(self):
        return self.to_pay_amount - self.amount_company_currency_signed_pro

    @api.depends('payment_total', 'to_pay_amount', 'amount_company_currency_signed_pro')
    def _compute_payment_difference(self):
        for rec in self:
            rec.payment_difference = rec._get_payment_difference()

    @api.depends('to_pay_move_line_ids', 'to_pay_move_line_ids.amount_residual')
    def _compute_selected_debt(self):
        for rec in self:
            # factor = 1
            rec.selected_debt = sum(rec.to_pay_move_line_ids._origin.mapped('amount_residual')) * (-1.0 if rec.partner_type == 'supplier' else 1.0)
            # TODO error en la creacion de un payment desde el menu?
            # if rec.payment_type == 'outbound' and rec.partner_type == 'customer' or \
            #         rec.payment_type == 'inbound' and rec.partner_type == 'supplier':
            #     factor = -1
            # rec.selected_debt = sum(rec.to_pay_move_line_ids._origin.mapped('amount_residual')) * factor

    @api.depends(
        'selected_debt', 'unreconciled_amount')
    def _compute_to_pay_amount(self):
        for rec in self:
            rec.to_pay_amount = rec.selected_debt + rec.unreconciled_amount

    @api.onchange('to_pay_amount')
    def _inverse_to_pay_amount(self):
        for rec in self:
            rec.unreconciled_amount = rec.to_pay_amount - rec.selected_debt

    @api.depends('partner_id', 'partner_type', 'company_id')
    def _compute_to_pay_move_lines(self):
        # TODO ?
        # # if payment group is being created from a payment we dont want to compute to_pay_move_lines
        # if self._context.get('created_automatically'):
        #     return

        # Se recomputan las lienas solo si la deuda que esta seleccionada solo si
        # cambio el partner, compania o partner_type
        for rec in self:
            if rec.partner_id != rec._origin.partner_id or rec.partner_type != rec._origin.partner_type or \
                    rec.company_id != rec._origin.company_id:
                rec.add_all()

    def _get_to_pay_move_lines_domain(self):
        self.ensure_one()
        return [
            ('partner_id.commercial_partner_id', '=', self.partner_id.commercial_partner_id.id),
            ('company_id', '=', self.company_id.id), ('move_id.state', '=', 'posted'),
            ('account_id.reconcile', '=', True), ('reconciled', '=', False), ('full_reconcile_id', '=', False),
            ('account_id.account_type', '=', 'asset_receivable' if self.partner_type == 'customer' else 'liability_payable'),
        ]

    def add_all(self):
        for rec in self:
            rec.to_pay_move_line_ids = [Command.clear(), Command.set(self.env['account.move.line'].search(rec._get_to_pay_move_lines_domain()).ids)]

    def remove_all(self):
        self.to_pay_move_line_ids = False

    @api.constrains('partner_id', 'to_pay_move_line_ids')
    def check_to_pay_lines(self):
        for rec in self:
            to_pay_partners = rec.to_pay_move_line_ids.mapped('partner_id')
            if len(to_pay_partners) > 1:
                raise ValidationError(_('All to pay lines must be of the same partner'))
            if len(rec.to_pay_move_line_ids.mapped('company_id')) > 1:
                raise ValidationError(_("You can't create payments for entries belonging to different companies."))
            if to_pay_partners and to_pay_partners != rec.partner_id.commercial_partner_id:
                raise ValidationError(_('Payment group for partner %s but payment lines are of partner %s') % (
                    rec.partner_id.name, to_pay_partners.name))

    def action_post(self):
        res = super().action_post()
        # Filtro porque los pagos electronicos solo pueden estar en pending si la transaccion esta en pending
        # y no los puedo conciliar esto no es un comportamiento del core
        # sino que esta implementado en account_payment_ux
        # posted_payments = rec.payment_ids.filtered(lambda x: x.state == 'posted')
        # if not created_automatically and posted_payments:
        created_automatically = self._context.get('created_automatically')

        for rec in self:
            if (rec.is_approved and rec.payment_difference and not created_automatically):
                raise ValidationError(_('To Pay Amount and Payment Amount must be equal!'))
            counterpart_aml = rec.mapped('line_ids').filtered(
                lambda r: not r.reconciled and r.account_id.account_type in self._get_valid_payment_account_types())
            if counterpart_aml and rec.to_pay_move_line_ids:
                (counterpart_aml + (rec.to_pay_move_line_ids)).reconcile()

        return res

    # --- ORM METHODS--- #
    def web_read(self, specification):
        fields_to_read = list(specification) or ['id']
        if 'matched_move_line_ids' in fields_to_read and 'context' in specification['matched_move_line_ids']:
            specification['matched_move_line_ids']['context'].update({'matched_payment_ids': self._ids})
        return super().web_read(specification)
