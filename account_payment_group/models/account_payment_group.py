# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, api, fields, _
from odoo.exceptions import ValidationError


MAP_PARTNER_TYPE_ACCOUNT_TYPE = {
    'customer': 'receivable',
    'supplier': 'payable',
}
MAP_ACCOUNT_TYPE_PARTNER_TYPE = {
    'receivable': 'customer',
    'payable': 'supplier',
}


class AccountPaymentGroup(models.Model):
    _name = "account.payment.group"
    _description = "Payment Group"
    _order = "payment_date desc"
    _inherit = 'mail.thread'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        index=True,
        change_default=True,
        default=lambda self: self.env.user.company_id,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    payment_methods = fields.Char(
        string='Payment Methods',
        compute='_compute_payment_methods',
        search='_search_payment_methods',
    )
    partner_type = fields.Selection(
        [('customer', 'Customer'), ('supplier', 'Vendor')],
        track_visibility='always',
        change_default=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        track_visibility='always',
        change_default=True,
        index=True,
    )
    commercial_partner_id = fields.Many2one(
        related='partner_id.commercial_partner_id',
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.user.company_id.currency_id,
        readonly=True,
        states={'draft': [('readonly', False)]},
        track_visibility='always',
    )
    payment_date = fields.Date(
        string='Payment Date',
        default=fields.Date.context_today,
        required=True,
        copy=False,
        readonly=True,
        states={'draft': [('readonly', False)]},
        index=True,
    )
    communication = fields.Char(
        string='Memo',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    notes = fields.Text(
        string='Notes'
    )
    matched_amount = fields.Monetary(
        compute='_compute_matched_amounts',
        currency_field='currency_id',
    )
    unmatched_amount = fields.Monetary(
        compute='_compute_matched_amounts',
        currency_field='currency_id',
    )
    selected_finacial_debt = fields.Monetary(
        string='Selected Financial Debt',
        compute='_compute_selected_debt',
    )
    selected_debt = fields.Monetary(
        # string='To Pay lines Amount',
        string='Selected Debt',
        compute='_compute_selected_debt',
    )
    # this field is to be used by others
    selected_debt_untaxed = fields.Monetary(
        # string='To Pay lines Amount',
        string='Selected Debt Untaxed',
        compute='_compute_selected_debt',
    )
    unreconciled_amount = fields.Monetary(
        string='Adjustment / Advance',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    # reconciled_amount = fields.Monetary(compute='_compute_amounts')
    to_pay_amount = fields.Monetary(
        compute='_compute_to_pay_amount',
        inverse='_inverse_to_pay_amount',
        string='To Pay Amount',
        # string='Total To Pay Amount',
        readonly=True,
        states={'draft': [('readonly', False)]},
        track_visibility='always',
    )
    payments_amount = fields.Monetary(
        compute='_compute_payments_amount',
        string='Amount',
        track_visibility='always',
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('posted', 'Posted'),
        # ('sent', 'Sent'),
        # ('reconciled', 'Reconciled')
        ('cancel', 'Cancelled'),
    ],
        readonly=True,
        default='draft',
        copy=False,
        string="Status",
        track_visibility='onchange',
        index=True,
    )
    move_lines_domain = [
        # ('partner_id.commercial_partner_id', '=', commercial_partner_id),
        # ('account_id.internal_type', '=', account_internal_type),
        ('account_id.reconcile', '=', True),
        ('reconciled', '=', False),
        # ('company_id', '=', company_id),
    ]
    debt_move_line_ids = fields.Many2many(
        'account.move.line',
        # por alguna razon el related no funciona bien ni con states ni
        # actualiza bien con el onchange, hacemos computado mejor
        compute='_compute_debt_move_line_ids',
        inverse='_inverse_debt_move_line_ids',
        string="Debt Lines",
        # no podemos ordenar por due date porque esta hardecodeado en
        # funcion _get_pair_to_reconcile
        help="Payment will be automatically matched with the oldest lines of "
        "this list (by date, no by maturity date). You can remove any line you"
        " dont want to be matched.",
        domain=move_lines_domain,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    has_outstanding = fields.Boolean(
        compute='_compute_has_outstanding',
    )
    to_pay_move_line_ids = fields.Many2many(
        'account.move.line',
        'account_move_line_payment_group_to_pay_rel',
        'payment_group_id',
        'to_pay_line_id',
        string="To Pay Lines",
        help='This lines are the ones the user has selected to be paid.',
        copy=False,
        domain=move_lines_domain,
        # lo hacemos readonly por vista y no por aca porque el relatd si no
        # no funcionaba bien
        readonly=True,
        states={'draft': [('readonly', False)]},
        auto_join=True,
    )
    matched_move_line_ids = fields.Many2many(
        'account.move.line',
        compute='_compute_matched_move_line_ids',
        help='Lines that has been matched to payments, only available after '
        'payment validation',
    )
    payment_subtype = fields.Char(
        compute='_compute_payment_subtype'
    )
    pop_up = fields.Boolean(
        # campo que agregamos porque el  invisible="context.get('pop_up')"
        # en las pages no se comportaba bien con los attrs
        compute='_compute_payment_pop_up',
        default=lambda x: x._context.get('pop_up', False),
    )
    payment_difference = fields.Monetary(
        compute='_compute_payment_difference',
        # TODO rename field or remove string
        # string='Remaining Residual',
        readonly=True,
        string="Payments Difference",
        help="Difference between selected debt (or to pay amount) and "
        "payments amount"
    )
    payment_ids = fields.One2many(
        'account.payment',
        'payment_group_id',
        string='Payment Lines',
        ondelete='cascade',
        copy=False,
        readonly=True,
        states={
            'draft': [('readonly', False)],
            'confirmed': [('readonly', False)]},
        auto_join=True,
    )
    account_internal_type = fields.Char(
        compute='_compute_account_internal_type'
    )
    move_line_ids = fields.Many2many(
        'account.move.line',
        # related o2m a o2m solo toma el primer o2m y le hace o2m, por eso
        # hacemos computed
        # related='payment_ids.move_line_ids',
        compute='_compute_move_lines',
        readonly=True,
        copy=False,
    )

    @api.multi
    @api.depends(
        'state',
        'payments_amount',
        'matched_move_line_ids.payment_group_matched_amount')
    def _compute_matched_amounts(self):
        for rec in self:
            if rec.state != 'posted':
                continue
            # damos vuelta signo porque el payments_amount tmb lo da vuelta,
            # en realidad porque siempre es positivo y se define en funcion
            # a si es pago entrante o saliente
            sign = rec.partner_type == 'supplier' and -1.0 or 1.0
            rec.matched_amount = sign * sum(
                rec.matched_move_line_ids.with_context(
                    payment_group_id=rec.id).mapped(
                        'payment_group_matched_amount'))
            rec.unmatched_amount = rec.payments_amount - rec.matched_amount

    @api.multi
    @api.depends('to_pay_move_line_ids')
    def _compute_has_outstanding(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            if rec.partner_type == 'supplier':
                # field = 'debit'
                lines = rec.to_pay_move_line_ids.filtered(
                    lambda x: x.amount_residual > 0.0)
            else:
                lines = rec.to_pay_move_line_ids.filtered(
                    lambda x: x.amount_residual < 0.0)
            if len(lines) != 0:
                rec.has_outstanding = True

    def _search_payment_methods(self, operator, value):
        return [('payment_ids.journal_id.name', operator, value)]

    @api.multi
    def _compute_payment_methods(self):
        # TODO tal vez sea interesante sumar al string el metodo en si mismo
        # (manual, cheque, etc)

        # tuvmos que hacerlo asi sudo porque si no tenemos error, si agregamos
        # el sudo al self o al rec no se computa el valor, probamos tmb
        # haciendo compute sudo y no anduvo, la unica otra alternativa que
        # funciono es el search de arriba (pero que no muestra todos los
        # names)
        for rec in self:
            # journals = rec.env['account.journal'].search(
            #     [('id', 'in', rec.payment_ids.ids)])
            # rec.payment_methods = ", ".join(journals.mapped('name'))
            rec.payment_methods = ", ".join(rec.payment_ids.sudo().mapped(
                'journal_id.name'))

    @api.multi
    def action_payment_sent(self):
        raise ValidationError(_('Not implemented yet'))

    @api.multi
    def payment_print(self):
        raise ValidationError(_('Not implemented yet'))

    @api.multi
    @api.depends('to_pay_move_line_ids')
    def _compute_debt_move_line_ids(self):
        for rec in self:
            rec.debt_move_line_ids = rec.to_pay_move_line_ids

    @api.multi
    @api.onchange('debt_move_line_ids')
    def _inverse_debt_move_line_ids(self):
        for rec in self:
            rec.to_pay_move_line_ids = rec.debt_move_line_ids

    @api.multi
    def _compute_payment_pop_up(self):
        pop_up = self._context.get('pop_up', False)
        for rec in self:
            rec.pop_up = pop_up

    @api.multi
    @api.depends('company_id.double_validation', 'partner_type')
    def _compute_payment_subtype(self):
        force_simple = self._context.get('force_simple')
        for rec in self:
            if (rec.partner_type == 'supplier' and
                    rec.company_id.double_validation and not force_simple):
                payment_subtype = 'double_validation'
            else:
                payment_subtype = 'simple'
            rec.payment_subtype = payment_subtype

    @api.multi
    def _compute_matched_move_line_ids(self):
        """
        Lar partial reconcile vinculan dos apuntes con credit_move_id y
        debit_move_id.
        Buscamos primeros todas las que tienen en credit_move_id algun apunte
        de los que se genero con un pago, etnonces la contrapartida
        (debit_move_id), son cosas que se pagaron con este pago. Repetimos
        al revz (debit_move_id vs credit_move_id)
        """
        for rec in self:
            lines = rec.move_line_ids.browse()
            # not sure why but self.move_line_ids dont work the same way
            payment_lines = rec.payment_ids.mapped('move_line_ids')

            reconciles = rec.env['account.partial.reconcile'].search([
                ('credit_move_id', 'in', payment_lines.ids)])
            lines |= reconciles.mapped('debit_move_id')

            reconciles = rec.env['account.partial.reconcile'].search([
                ('debit_move_id', 'in', payment_lines.ids)])
            lines |= reconciles.mapped('credit_move_id')

            rec.matched_move_line_ids = lines - payment_lines

    @api.multi
    @api.depends('payment_ids.move_line_ids')
    def _compute_move_lines(self):
        for rec in self:
            rec.move_line_ids = rec.payment_ids.mapped('move_line_ids')

    @api.multi
    @api.depends('partner_type')
    def _compute_account_internal_type(self):
        for rec in self:
            if rec.partner_type:
                rec.account_internal_type = MAP_PARTNER_TYPE_ACCOUNT_TYPE[
                    rec.partner_type]

    @api.multi
    @api.depends('to_pay_amount', 'payments_amount')
    def _compute_payment_difference(self):
        for rec in self:
            # if rec.payment_subtype != 'double_validation':
            #     continue
            rec.payment_difference = rec.to_pay_amount - rec.payments_amount

    @api.multi
    @api.depends('payment_ids.signed_amount_company_currency')
    def _compute_payments_amount(self):
        for rec in self:
            rec.payments_amount = sum(rec.payment_ids.mapped(
                'signed_amount_company_currency'))
            # payments_amount = sum([
            #     x.payment_type == 'inbound' and
            #     x.amount_company_currency or -x.amount_company_currency for
            #     x in rec.payment_ids])
            # rec.payments_amount = (
            #     rec.partner_type == 'supplier' and
            #     -payments_amount or payments_amount)

    @api.multi
    @api.depends(
        'to_pay_move_line_ids.amount_residual',
        'to_pay_move_line_ids.amount_residual_currency',
        'to_pay_move_line_ids.currency_id',
        'to_pay_move_line_ids.invoice_id',
        'payment_date',
        'currency_id',
    )
    def _compute_selected_debt(self):
        for rec in self:
            selected_finacial_debt = 0.0
            selected_debt = 0.0
            selected_debt_untaxed = 0.0
            for line in rec.to_pay_move_line_ids:
                selected_finacial_debt += line.financial_amount_residual
                selected_debt += line.amount_residual
                # factor for total_untaxed
                invoice = line.invoice_id
                factor = invoice and invoice._get_tax_factor() or 1.0
                selected_debt_untaxed += line.amount_residual * factor
            sign = rec.partner_type == 'supplier' and -1.0 or 1.0
            rec.selected_finacial_debt = selected_finacial_debt * sign
            rec.selected_debt = selected_debt * sign
            rec.selected_debt_untaxed = selected_debt_untaxed * sign

    @api.multi
    @api.depends(
        'selected_debt', 'unreconciled_amount')
    def _compute_to_pay_amount(self):
        for rec in self:
            rec.to_pay_amount = rec.selected_debt + rec.unreconciled_amount

    @api.multi
    @api.onchange('to_pay_amount')
    def _inverse_to_pay_amount(self):
        for rec in self:
            rec.unreconciled_amount = rec.to_pay_amount - rec.selected_debt

    @api.multi
    @api.onchange('partner_id', 'partner_type', 'company_id')
    def _refresh_payments_and_move_lines(self):
        # clean actual invoice and payments
        # no hace falta
        if self._context.get('pop_up'):
            return
        for rec in self:
            rec.payment_ids = [(2, item.id, 0) for item in rec.payment_ids]
            rec.add_all()

    @api.multi
    def onchange(self, values, field_name, field_onchange):
        """Necesitamos hacer esto porque los onchange que agregan lineas,
        cuando se va a guardar el registro, terminan creando registros.
        """
        fields = []
        for field in field_onchange.keys():
            if field.startswith((
                    'to_pay_move_line_ids.',
                    'debt_move_line_ids.')):
                fields.append(field)
        for field in fields:
            del field_onchange[field]
        return super(AccountPaymentGroup, self).onchange(
            values, field_name, field_onchange)

    @api.multi
    def _get_to_pay_move_lines_domain(self):
        self.ensure_one()
        return [
            ('partner_id.commercial_partner_id', '=',
                self.commercial_partner_id.id),
            ('account_id.internal_type', '=',
                self.account_internal_type),
            ('account_id.reconcile', '=', True),
            ('reconciled', '=', False),
            ('company_id', '=', self.company_id.id),
            # '|',
            # ('amount_residual', '!=', False),
            # ('amount_residual_currency', '!=', False),
        ]

    @api.multi
    def add_all(self):
        for rec in self:
            rec.to_pay_move_line_ids = rec.env['account.move.line'].search(
                rec._get_to_pay_move_lines_domain())

    @api.multi
    def remove_all(self):
        self.to_pay_move_line_ids = False

    @api.model
    def default_get(self, fields):
        # TODO si usamos los move lines esto no haria falta
        rec = super(AccountPaymentGroup, self).default_get(fields)
        to_pay_move_line_ids = self._context.get('to_pay_move_line_ids')
        to_pay_move_lines = self.env['account.move.line'].browse(
            to_pay_move_line_ids).filtered(lambda x: (
                x.account_id.reconcile and
                x.account_id.internal_type in ('receivable', 'payable')))
        if to_pay_move_lines:
            partner = to_pay_move_lines.mapped('partner_id')
            if len(partner) != 1:
                raise ValidationError(_(
                    'You can not send to pay lines from different partners'))

            internal_type = to_pay_move_lines.mapped(
                'account_id.internal_type')
            if len(internal_type) != 1:
                raise ValidationError(_(
                    'You can not send to pay lines from different partners'))
            rec['partner_id'] = self._context.get(
                'default_partner_id', partner[0].id)
            rec['partner_type'] = MAP_ACCOUNT_TYPE_PARTNER_TYPE[
                internal_type[0]]
            # rec['currency_id'] = invoice['currency_id'][0]
            # rec['payment_type'] = (
            #     internal_type[0] == 'receivable' and
            #     'inbound' or 'outbound')
            rec['to_pay_move_line_ids'] = [(6, False, to_pay_move_line_ids)]
        return rec

    @api.multi
    def button_journal_entries(self):
        return {
            'name': _('Journal Items'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('payment_id', 'in', self.payment_ids.ids)],
        }

    @api.multi
    def unreconcile(self):
        for rec in self:
            rec.payment_ids.unreconcile()
        # TODO en alguos casos setear sent como en payment?
        self.write({'state': 'posted'})

    @api.multi
    def cancel(self):
        for rec in self:
            # because child payments dont have invoices we remove reconcile
            for move in rec.move_line_ids.mapped('move_id'):
                rec.matched_move_line_ids.remove_move_reconcile()
                # TODO borrar esto si con el de arriba va bien
                # if rec.to_pay_move_line_ids:
                #     move.line_ids.remove_move_reconcile()
            rec.payment_ids.cancel()
            rec.payment_ids.write({'invoice_ids': [(5, 0, 0)]})
        self.write({'state': 'cancel'})

    @api.multi
    def action_draft(self):
        self.mapped('payment_ids').action_draft()
        return self.write({'state': 'draft'})

    @api.multi
    def unlink(self):
        if any(rec.state != 'draft' for rec in self):
            raise ValidationError(_(
                "You can not delete a payment that is already posted"))
        return super(AccountPaymentGroup, self).unlink()

    @api.multi
    def confirm(self):
        for rec in self:
            accounts = rec.to_pay_move_line_ids.mapped('account_id')
            if len(accounts) > 1:
                raise ValidationError(_(
                    'To Pay Lines must be of the same account!'))
        self.write({'state': 'confirmed'})

    @api.multi
    def post(self):
        # dont know yet why, but if we came from an invoice context values
        # break behaviour, for eg. with demo user error writing account.account
        # and with other users, error with block date of accounting
        # TODO we should look for a better way to solve this

        create_from_website = self._context.get(
            'create_from_website', False)
        create_from_statement = self._context.get(
            'create_from_statement', False)
        create_from_expense = self._context.get('create_from_expense', False)
        self = self.with_context({})
        for rec in self:
            # TODO if we want to allow writeoff then we can disable this
            # constrain and send writeoff_journal_id and writeoff_acc_id
            if not rec.payment_ids:
                raise ValidationError(_(
                    'You can not confirm a payment group without payment '
                    'lines!'))
            # si el pago se esta posteando desde statements y hay doble
            # validacion no verificamos que haya deuda seleccionada
            if (rec.payment_subtype == 'double_validation' and
                    rec.payment_difference and (not create_from_statement and
                                                not create_from_expense)):
                raise ValidationError(_(
                    'To Pay Amount and Payment Amount must be equal!'))

            writeoff_acc_id = False
            writeoff_journal_id = False

            # al crear desde website odoo crea primero el pago y lo postea
            # y no debemos re-postearlo
            if not create_from_website and not create_from_expense:
                rec.payment_ids.filtered(lambda x: x.state == 'draft').post()

            counterpart_aml = rec.payment_ids.mapped('move_line_ids').filtered(
                lambda r: not r.reconciled and r.account_id.internal_type in (
                    'payable', 'receivable'))

            # porque la cuenta podria ser no recivible y ni conciliable
            # (por ejemplo en sipreco)
            if counterpart_aml and rec.to_pay_move_line_ids:
                (counterpart_aml + (rec.to_pay_move_line_ids)).reconcile(
                    writeoff_acc_id, writeoff_journal_id)

            rec.state = 'posted'
