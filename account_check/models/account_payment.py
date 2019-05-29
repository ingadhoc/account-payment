##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models, _, api
from odoo.exceptions import UserError, ValidationError
import logging
# import odoo.addons.decimal_precision as dp
_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):

    _inherit = 'account.payment'

    check_ids = fields.Many2many(
        'account.check',
        string='Checks',
        copy=False,
        readonly=True,
        states={'draft': [('readonly', False)]},
        auto_join=True,
    )
    # only for v8 comatibility where more than one check could be received
    # or issued
    check_ids_copy = fields.Many2many(
        related='check_ids',
        readonly=True,
    )
    readonly_currency_id = fields.Many2one(
        related='currency_id',
        readonly=True,
    )
    readonly_amount = fields.Monetary(
        related='amount',
        readonly=True,
    )
    # we add this field for better usability on issue checks and received
    # checks. We keep m2m field for backward compatibility where we allow to
    # use more than one check per payment
    check_id = fields.Many2one(
        'account.check',
        compute='_compute_check',
        string='Check',
    )
    check_deposit_type = fields.Selection(
        [('consolidated', 'Consolidated'),
         ('detailed', 'Detailed')],
        default='detailed',
        help="This option is relevant if you use bank statements. Detailed is"
        " used when the bank credits one by one the checks, consolidated is"
        " for when the bank credits all the checks in a single movement",
    )

    @api.multi
    @api.depends('check_ids')
    def _compute_check(self):
        for rec in self:
            # we only show checks for issue checks or received thid checks
            # if len of checks is 1
            if rec.payment_method_code in (
                    'received_third_check',
                    'issue_check',) and len(rec.check_ids) == 1:
                rec.check_id = rec.check_ids[0].id

# check fields, just to make it easy to load checks without need to create
# them by a m2o record
    check_name = fields.Char(
        'Check Name',
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]},
    )
    check_number = fields.Integer(
        'Check Number',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=False,
    )
    check_issue_date = fields.Date(
        'Check Issue Date',
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]},
        default=fields.Date.context_today,
    )
    check_payment_date = fields.Date(
        'Check Payment Date',
        readonly=True,
        help="Only if this check is post dated",
        states={'draft': [('readonly', False)]},
    )
    checkbook_id = fields.Many2one(
        'account.checkbook',
        'Checkbook',
        readonly=True,
        states={'draft': [('readonly', False)]},
        auto_join=True,
    )
    check_subtype = fields.Selection(
        related='checkbook_id.issue_check_subtype',
        readonly=True,
    )
    check_bank_id = fields.Many2one(
        'res.bank',
        'Check Bank',
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]},
        auto_join=True,
    )
    check_owner_vat = fields.Char(
        'Check Owner Vat',
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]}
    )
    check_owner_name = fields.Char(
        'Check Owner Name',
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]}
    )
    # this fields is to help with code and view
    check_type = fields.Char(
        compute='_compute_check_type',
    )
    checkbook_numerate_on_printing = fields.Boolean(
        related='checkbook_id.numerate_on_printing',
        readonly=True,
    )
    # TODO borrar, esto estaria depreciado
    # checkbook_block_manual_number = fields.Boolean(
    #     related='checkbook_id.block_manual_number',
    #     readonly=True,
    # )
    # check_number_readonly = fields.Integer(
    #     related='check_number',
    #     readonly=True,
    # )

    @api.multi
    @api.depends('payment_method_code')
    def _compute_check_type(self):
        for rec in self:
            if rec.payment_method_code == 'issue_check':
                rec.check_type = 'issue_check'
            elif rec.payment_method_code in [
                    'received_third_check',
                    'delivered_third_check']:
                rec.check_type = 'third_check'

    @api.multi
    def _compute_payment_method_description(self):
        check_payments = self.filtered(
            lambda x: x.payment_method_code in
            ['issue_check', 'received_third_check', 'delivered_third_check'])
        for rec in check_payments:
            if rec.check_ids:
                checks_desc = ', '.join(rec.check_ids.mapped('name'))
            else:
                checks_desc = rec.check_name
            name = "%s: %s" % (rec.payment_method_id.display_name, checks_desc)
            rec.payment_method_description = name
        return super(
            AccountPayment,
            (self - check_payments))._compute_payment_method_description()

# on change methods

    @api.constrains('check_ids')
    @api.onchange('check_ids', 'payment_method_code')
    def onchange_checks(self):
        for rec in self:
            # we only overwrite if payment method is delivered
            if rec.payment_method_code == 'delivered_third_check':
                rec.amount = sum(rec.check_ids.mapped('amount'))
                currency = rec.check_ids.mapped('currency_id')

                if len(currency) > 1:
                    raise ValidationError(_(
                        'You are trying to deposit checks of difference'
                        ' currencies, this functionality is not supported'))
                elif len(currency) == 1:
                    rec.currency_id = currency.id

                # si es una entrega de cheques de terceros y es en otra moneda
                # a la de la cia, forzamos el importe en moneda de cia de los
                # cheques originales
                # escribimos force_amount_company_currency directamente en vez
                # de amount_company_currency por lo explicado en
                # _inverse_amount_company_currency
                if rec.currency_id != rec.company_currency_id:
                    rec.force_amount_company_currency = sum(
                        rec.check_ids.mapped('amount_company_currency'))

    @api.onchange('amount_company_currency')
    def _inverse_amount_company_currency(self):
        # el metodo _inverse_amount_company_currency tiene un parche feo de
        # un onchange sobre si mismo que termina haciendo que se vuelva a
        # ejecutar y entonces no siempre guarde el importe en otra moneda
        # habria que eliminar ese onchange, por el momento anulando
        # eso para los cheques de terceros y escribiendo directamente
        # force_amount_company_currency, lo solucionamos
        self = self.filtered(
            lambda x: x.payment_method_code != 'delivered_third_check')
        return super(AccountPayment, self)._inverse_amount_company_currency()

    @api.multi
    @api.onchange('check_number')
    def change_check_number(self):
        # TODO make default padding a parameter
        def _get_name_from_number(number):
            padding = 8
            if len(str(number)) > padding:
                padding = len(str(number))
            return ('%%0%sd' % padding % number)

        for rec in self:
            if rec.payment_method_code in ['received_third_check']:
                if not rec.check_number:
                    check_name = False
                else:
                    check_name = _get_name_from_number(rec.check_number)
                rec.check_name = check_name
            elif rec.payment_method_code in ['issue_check']:
                sequence = rec.checkbook_id.sequence_id
                if not rec.check_number:
                    check_name = False
                elif sequence:
                    if rec.check_number != sequence.number_next_actual:
                        # write with sudo for access rights over sequence
                        sequence.sudo().write(
                            {'number_next_actual': rec.check_number})
                    check_name = rec.checkbook_id.sequence_id.next_by_id()
                else:
                    # in sipreco, for eg, no sequence on checkbooks
                    check_name = _get_name_from_number(rec.check_number)
                rec.check_name = check_name

    @api.onchange('check_issue_date', 'check_payment_date')
    def onchange_date(self):
        if (
                self.check_issue_date and self.check_payment_date and
                self.check_issue_date > self.check_payment_date):
            self.check_payment_date = False
            raise UserError(
                _('Check Payment Date must be greater than Issue Date'))

    @api.onchange('check_owner_vat')
    def onchange_check_owner_vat(self):
        """
        We suggest owner name from owner vat
        """
        # if not self.check_owner_name:
        self.check_owner_name = self.search(
            [('check_owner_vat', '=', self.check_owner_vat)],
            limit=1).check_owner_name

    @api.onchange('partner_id', 'payment_method_code')
    def onchange_partner_check(self):
        commercial_partner = self.partner_id.commercial_partner_id
        if self.payment_method_code == 'received_third_check':
            self.check_bank_id = (
                commercial_partner.bank_ids and
                commercial_partner.bank_ids[0].bank_id or False)
            # en realidad se termina pisando con onchange_check_owner_vat
            # entonces llevamos nombre solo si ya existe la priemr vez
            # TODO ver si lo mejoramos o borramos esto directamente
            # self.check_owner_name = commercial_partner.name
            vat_field = 'vat'
            # to avoid needed of another module, we add this check to see
            # if l10n_ar cuit field is available
            if 'cuit' in commercial_partner._fields:
                vat_field = 'cuit'
            self.check_owner_vat = commercial_partner[vat_field]
        elif self.payment_method_code == 'issue_check':
            self.check_bank_id = self.journal_id.bank_id
            self.check_owner_name = False
            self.check_owner_vat = False
        # no hace falta else porque no se usa en otros casos

    @api.onchange('payment_method_code')
    def _onchange_payment_method_code(self):
        if self.payment_method_code == 'issue_check':
            checkbook = self.env['account.checkbook'].search([
                ('state', '=', 'active'),
                ('journal_id', '=', self.journal_id.id)],
                limit=1)
            self.checkbook_id = checkbook
        elif self.checkbook_id:
            # TODO ver si interesa implementar volver atras numeracion
            self.checkbook_id = False
        # si cambiamos metodo de pago queremos refrescar listado de cheques
        # seleccionados
        self.check_ids = False

    @api.onchange('checkbook_id')
    def onchange_checkbook(self):
        if self.checkbook_id and not self.checkbook_id.numerate_on_printing:
            self.check_number = self.checkbook_id.next_number
        else:
            self.check_number = False

# post methods
    @api.multi
    def cancel(self):
        for rec in self:
            # solo cancelar operaciones si estaba postead, por ej para comp.
            # con pagos confirmados, se cancelan pero no hay que deshacer nada
            # de asientos ni cheques
            if rec.state in ['confirmed', 'posted']:
                rec.do_checks_operations(cancel=True)
        res = super(AccountPayment, self).cancel()
        return res

    @api.multi
    def create_check(self, check_type, operation, bank):
        self.ensure_one()

        check_vals = {
            'bank_id': bank.id,
            'owner_name': self.check_owner_name,
            'owner_vat': self.check_owner_vat,
            'number': self.check_number,
            'name': self.check_name,
            'checkbook_id': self.checkbook_id.id,
            'issue_date': self.check_issue_date,
            'type': self.check_type,
            'journal_id': self.journal_id.id,
            'amount': self.amount,
            'payment_date': self.check_payment_date,
            'currency_id': self.currency_id.id,
            'amount_company_currency': self.amount_company_currency,
        }

        check = self.env['account.check'].create(check_vals)
        self.check_ids = [(4, check.id, False)]
        check._add_operation(
            operation, self, self.partner_id, date=self.payment_date)
        return check

    @api.multi
    def do_checks_operations(self, vals=None, cancel=False):
        """
        Check attached .ods file on this module to understand checks workflows
        This method is called from:
        * cancellation of payment to execute delete the right operation and
            unlink check if needed
        * from _get_liquidity_move_line_vals to add check operation and, if
            needded, change payment vals and/or create check and
        TODO si queremos todos los del operation podriamos moverlos afuera y
        simplificarlo ya que es el mismo en casi todos
        Tambien podemos simplficiar las distintas opciones y como se recorren
        los if
        """
        self.ensure_one()
        rec = self
        if not rec.check_type:
            # continue
            return vals
        if (
                rec.payment_method_code == 'received_third_check' and
                rec.payment_type == 'inbound'
                # el chequeo de partner type no seria necesario
                # un proveedor nos podria devolver plata con un cheque
                # and rec.partner_type == 'customer'
        ):
            operation = 'holding'
            if cancel:
                _logger.info('Cancel Receive Check')
                rec.check_ids._del_operation(self)
                rec.check_ids.unlink()
                return None

            _logger.info('Receive Check')
            check = self.create_check(
                'third_check', operation, self.check_bank_id)
            vals['date_maturity'] = self.check_payment_date
            vals['account_id'] = check.get_third_check_account().id
            vals['name'] = _('Receive check %s') % check.name
        elif (
                rec.payment_method_code == 'delivered_third_check' and
                rec.payment_type == 'transfer'):
            # si el cheque es entregado en una transferencia tenemos tres
            # opciones
            # TODO we should make this method selectable for transfers
            inbound_method = (
                rec.destination_journal_id.inbound_payment_method_ids)
            # si un solo inbound method y es received third check
            # entonces consideramos que se esta moviendo el cheque de un diario
            # al otro
            if len(inbound_method) == 1 and (
                    inbound_method.code == 'received_third_check'):
                if cancel:
                    _logger.info('Cancel Transfer Check')
                    for check in rec.check_ids:
                        check._del_operation(self)
                        check._del_operation(self)
                        receive_op = check._get_operation('holding')
                        if receive_op.origin._name == 'account.payment':
                            check.journal_id = receive_op.origin.journal_id.id
                    return None

                _logger.info('Transfer Check')
                rec.check_ids._add_operation(
                    'transfered', rec, False, date=rec.payment_date)
                rec.check_ids._add_operation(
                    'holding', rec, False, date=rec.payment_date)
                rec.check_ids.write({
                    'journal_id': rec.destination_journal_id.id})
                vals['account_id'] = rec.check_ids.get_third_check_account().id
                vals['name'] = _('Transfer checks %s') % ', '.join(
                    rec.check_ids.mapped('name'))
            elif rec.destination_journal_id.type == 'cash':
                if cancel:
                    _logger.info('Cancel Sell Check')
                    rec.check_ids._del_operation(self)
                    return None

                _logger.info('Sell Check')
                rec.check_ids._add_operation(
                    'selled', rec, False, date=rec.payment_date)
                vals['account_id'] = rec.check_ids.get_third_check_account().id
                vals['name'] = _('Sell check %s') % ', '.join(
                    rec.check_ids.mapped('name'))
            # bank
            else:
                if cancel:
                    _logger.info('Cancel Deposit Check')
                    rec.check_ids._del_operation(self)
                    return None

                _logger.info('Deposit Check')
                rec.check_ids._add_operation(
                    'deposited', rec, False, date=rec.payment_date)
                vals['account_id'] = rec.check_ids.get_third_check_account().id
                vals['name'] = _('Deposit checks %s') % ', '.join(
                    rec.check_ids.mapped('name'))
        elif (
                rec.payment_method_code == 'delivered_third_check' and
                rec.payment_type == 'outbound'
                # el chequeo del partner type no es necesario
                # podriamos entregarlo a un cliente
                # and rec.partner_type == 'supplier'
        ):
            if cancel:
                _logger.info('Cancel Deliver Check')
                rec.check_ids._del_operation(self)
                return None

            _logger.info('Deliver Check')
            rec.check_ids._add_operation(
                'delivered', rec, rec.partner_id, date=rec.payment_date)
            vals['account_id'] = rec.check_ids.get_third_check_account().id
            vals['name'] = _('Deliver checks %s') % ', '.join(
                rec.check_ids.mapped('name'))
        elif (
                rec.payment_method_code == 'issue_check' and
                rec.payment_type == 'outbound'
                # el chequeo del partner type no es necesario
                # podriamos entregarlo a un cliente
                # and rec.partner_type == 'supplier'
        ):
            if cancel:
                _logger.info('Cancel Hand/debit Check')
                rec.check_ids._del_operation(self)
                rec.check_ids.unlink()
                return None

            _logger.info('Hand/debit Check')
            # if check is deferred, hand it and later debit it change account
            # if check is current, debit it directly
            # operation = 'debited'
            # al final por ahora depreciamos esto ya que deberiamos adaptar
            # rechazos y demas, deferred solamente sin fecha pero con cuenta
            # puente
            # if self.check_subtype == 'deferred':
            vals['account_id'] = self.company_id._get_check_account(
                'deferred').id
            operation = 'handed'
            check = self.create_check(
                'issue_check', operation, self.check_bank_id)
            vals['date_maturity'] = self.check_payment_date
            vals['name'] = _('Hand check %s') % check.name
        elif (
                rec.payment_method_code == 'issue_check' and
                rec.payment_type == 'transfer' and
                rec.destination_journal_id.type == 'cash'):
            if cancel:
                _logger.info('Cancel Withdrawal Check')
                rec.check_ids._del_operation(self)
                rec.check_ids.unlink()
                return None

            _logger.info('Withdraw Check')
            self.create_check('issue_check', 'withdrawed', self.check_bank_id)
            vals['name'] = _('Withdraw with checks %s') % ', '.join(
                rec.check_ids.mapped('name'))
            vals['date_maturity'] = self.check_payment_date
            # if check is deferred, change account
            # si retiramos por caja directamente lo sacamos de banco
            # if self.check_subtype == 'deferred':
            #     vals['account_id'] = self.company_id._get_check_account(
            #         'deferred').id
        else:
            raise UserError(_(
                'This operatios is not implemented for checks:\n'
                '* Payment type: %s\n'
                '* Partner type: %s\n'
                '* Payment method: %s\n'
                '* Destination journal: %s\n' % (
                    rec.payment_type,
                    rec.partner_type,
                    rec.payment_method_code,
                    rec.destination_journal_id.type)))
        return vals

    @api.multi
    def post(self):
        for rec in self:
            if rec.check_ids and not rec.currency_id.is_zero(
                    sum(rec.check_ids.mapped('amount')) - rec.amount):
                raise UserError(_(
                    'La suma del pago no coincide con la suma de los cheques '
                    'seleccionados. Por favor intente eliminar y volver a '
                    'agregar un cheque.'))
            if rec.payment_method_code == 'issue_check' and (
                    not rec.check_number or not rec.check_name):
                raise UserError(_(
                    'Para mandar a proceso de firma debe definir número '
                    'de cheque en cada línea de pago.\n'
                    '* ID del pago: %s') % rec.id)
        res = super(AccountPayment, self).post()
        return res

    def _get_liquidity_move_line_vals(self, amount):
        vals = super(AccountPayment, self)._get_liquidity_move_line_vals(
            amount)
        vals = self.do_checks_operations(vals=vals)
        return vals

    @api.multi
    def do_print_checks(self):
        # si cambiamos nombre de check_report tener en cuenta en sipreco
        checkbook = self.mapped('checkbook_id')
        # si todos los cheques son de la misma chequera entonces buscamos
        # reporte específico para esa chequera
        report_name = len(checkbook) == 1 and  \
            checkbook.report_template.report_name \
            or 'check_report'
        check_report = self.env['ir.actions.report'].search(
            [('report_name', '=', report_name)], limit=1).report_action(self)
        # ya el buscar el reporte da el error solo
        # if not check_report:
        #     raise UserError(_(
        #       "There is no check report configured.\nMake sure to configure "
        #       "a check report named 'account_check_report'."))
        return check_report

    @api.multi
    def print_checks(self):
        if len(self.mapped('checkbook_id')) != 1:
            raise UserError(_(
                "In order to print multiple checks at once, they must belong "
                "to the same checkbook."))
        # por ahora preferimos no postearlos
        # self.filtered(lambda r: r.state == 'draft').post()

        # si numerar al imprimir entonces llamamos al wizard
        if self[0].checkbook_id.numerate_on_printing:
            if all([not x.check_name for x in self]):
                next_check_number = self[0].checkbook_id.next_number
                return {
                    'name': _('Print Pre-numbered Checks'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'print.prenumbered.checks',
                    'view_type': 'form',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'payment_ids': self.ids,
                        'default_next_check_number': next_check_number,
                    }
                }
            # si ya están enumerados mandamos a imprimir directamente
            elif all([x.check_name for x in self]):
                return self.do_print_checks()
            else:
                raise UserError(_(
                    'Está queriendo imprimir y enumerar cheques que ya han '
                    'sido numerados. Seleccione solo cheques numerados o solo'
                    ' cheques sin número.'))
        else:
            return self.do_print_checks()

    def _get_counterpart_move_line_vals(self, invoice=False):
        vals = super(AccountPayment, self)._get_counterpart_move_line_vals(
            invoice=invoice)
        force_account_id = self._context.get('force_account_id')
        if force_account_id:
            vals['account_id'] = force_account_id
        return vals

    @api.multi
    def _split_aml_line_per_check(self, move):
        """ Take an account mvoe, find the move lines related to check and
        split them one per earch check related to the payment
        """
        self.ensure_one()
        res = self.env['account.move.line']
        move.button_cancel()
        checks = self.check_ids
        aml = move.line_ids.with_context(check_move_validity=False).filtered(
            lambda x: x.name != self.name)
        if len(aml) > 1:
            raise UserError(
                _('Seems like this move has been already splited'))
        elif len(aml) == 0:
            raise UserError(
                _('There is not move lines to split'))

        amount_field = 'credit' if aml.credit else 'debit'
        new_name = _('Deposit check %s') if aml.credit else \
            aml.name + _(' check %s')

        # if the move line has currency then we are delivering checks on a
        # different currency than company one
        currency = aml.currency_id
        currency_sign = amount_field == 'debit' and 1.0 or -1.0
        aml.write({
            'name': new_name % checks[0].name,
            amount_field: checks[0].amount_company_currency,
            'amount_currency': currency and currency_sign * checks[0].amount,
        })
        res |= aml
        checks -= checks[0]
        for check in checks:
            res |= aml.copy({
                'name': new_name % check.name,
                amount_field: check.amount_company_currency,
                'payment_id': self.id,
                'amount_currency': currency and currency_sign * check.amount,
            })
        move.post()
        return res

    @api.multi
    def _create_payment_entry(self, amount):
        move = super(AccountPayment, self)._create_payment_entry(amount)
        if self.filtered(
            lambda x: x.payment_type == 'transfer' and
                x.payment_method_code == 'delivered_third_check' and
                x.check_deposit_type == 'detailed'):
            self._split_aml_line_per_check(move)
        return move

    @api.multi
    def _create_transfer_entry(self, amount):
        transfer_debit_aml = super(
            AccountPayment, self)._create_transfer_entry(amount)
        if self.filtered(
            lambda x: x.payment_type == 'transfer' and
                x.payment_method_code == 'delivered_third_check' and
                x.check_deposit_type == 'detailed'):
            self._split_aml_line_per_check(transfer_debit_aml.move_id)
        return transfer_debit_aml
