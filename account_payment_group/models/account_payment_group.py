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
        default=lambda self: self.env.company,
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
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        readonly=True,
        states={'draft': [('readonly', False)]},
        track_visibility='always',
    )
    payment_date = fields.Date(
        string='Payment Date',
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
    matched_amount_untaxed = fields.Monetary(
        compute='_compute_matched_amount_untaxed',
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
        domain=[
            # ('partner_id.commercial_partner_id', '=', commercial_partner_id),
            # ('account_id.internal_type', '=', account_internal_type),
            ('move_id.state', '=', 'posted'),
            ('account_id.reconcile', '=', True),
            ('reconciled', '=', False),
            ('full_reconcile_id', '=', False),
            # ('company_id', '=', company_id),
        ],
        readonly=True,
        states={'draft': [('readonly', False)]},
        # auto_join not yet implemented for m2m. TODO enable when implemented
        # https://github.com/odoo/odoo/blob/master/odoo/osv/expression.py#L899
        # auto_join=True,
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
    sent = fields.Boolean(
        readonly=True,
        default=False,
        copy=False,
        help="It indicates that the receipt has been sent."
    )

    @api.depends(
        'state',
        'payments_amount',
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
                rec.matched_move_line_ids.with_context(payment_group_id=rec.id).mapped('payment_group_matched_amount'))
            rec.unmatched_amount = rec.payments_amount - rec.matched_amount

    def _compute_matched_amount_untaxed(self):
        """ Lo separamos en otro metodo ya que es un poco mas costoso y no se
        usa en conjunto con matched_amount
        """
        for rec in self:
            rec.matched_amount_untaxed = 0.0
            if rec.state != 'posted':
                continue
            matched_amount_untaxed = 0.0
            sign = rec.partner_type == 'supplier' and -1.0 or 1.0
            for line in rec.matched_move_line_ids.with_context(
                    payment_group_id=rec.id):
                invoice = line.move_id
                factor = invoice and invoice._get_tax_factor() or 1.0
                matched_amount_untaxed += \
                    line.payment_group_matched_amount * factor
            rec.matched_amount_untaxed = sign * matched_amount_untaxed

    @api.depends('to_pay_move_line_ids')
    def _compute_has_outstanding(self):
        for rec in self:
            rec.has_outstanding = False
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
        recs = self.search([('payment_ids.journal_id.name', operator, value)])
        return [('id', 'in', recs.ids)]

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

    def action_payment_sent(self):
        """ Open a window to compose an email, with the edi payment template
            message loaded by default
        """
        self.ensure_one()
        template = self.env.ref(
            'account_payment_group.email_template_edi_payment_group',
            False)
        compose_form = self.env.ref(
            'mail.email_compose_message_wizard_form', False)
        ctx = dict(
            default_model='account.payment.group',
            default_res_id=self.id,
            default_use_template=bool(template),
            default_template_id=template and template.id or False,
            default_composition_mode='comment',
            mark_payment_as_sent=True,
        )
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }

    def payment_print(self):
        self.ensure_one()
        self.sent = True

        # if we print caming from other model then active id and active model
        # is wrong and it raise an error with custom filename
        self = self.with_context(
            active_model=self._name, active_id=self.id, active_ids=self.ids)

        return self.env.ref('account_payment_group.action_report_payment_group').report_action(self)

    def _compute_payment_pop_up(self):
        pop_up = self._context.get('pop_up', False)
        for rec in self:
            rec.pop_up = pop_up

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

    @api.depends('payment_ids.move_line_ids')
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
            payment_lines = rec.payment_ids.mapped('move_line_ids').filtered(lambda x: x.account_internal_type in ['receivable', 'payable'])
            rec.matched_move_line_ids =  (payment_lines.mapped('matched_debit_ids.debit_move_id') | payment_lines.mapped('matched_credit_ids.credit_move_id')) - payment_lines

    @api.depends('payment_ids.move_line_ids')
    def _compute_move_lines(self):
        for rec in self:
            rec.move_line_ids = rec.payment_ids.mapped('move_line_ids')

    @api.depends('partner_type')
    def _compute_account_internal_type(self):
        for rec in self:
            if rec.partner_type:
                rec.account_internal_type = MAP_PARTNER_TYPE_ACCOUNT_TYPE[
                    rec.partner_type]
            else:
                rec.account_internal_type = False

    @api.depends('to_pay_amount', 'payments_amount')
    def _compute_payment_difference(self):
        for rec in self:
            # if rec.payment_subtype != 'double_validation':
            #     continue
            rec.payment_difference = rec.to_pay_amount - rec.payments_amount

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

    @api.depends(
        'to_pay_move_line_ids.amount_residual',
        'to_pay_move_line_ids.amount_residual_currency',
        'to_pay_move_line_ids.currency_id',
        'to_pay_move_line_ids.move_id',
        'payment_date',
        'currency_id',
    )
    def _compute_selected_debt(self):
        for rec in self:
            selected_finacial_debt = 0.0
            selected_debt = 0.0
            selected_debt_untaxed = 0.0
            for line in rec.to_pay_move_line_ids._origin:
                selected_finacial_debt += line.financial_amount_residual
                selected_debt += line.amount_residual
                # factor for total_untaxed
                invoice = line.move_id
                factor = invoice and invoice._get_tax_factor() or 1.0
                selected_debt_untaxed += line.amount_residual * factor
            sign = rec.partner_type == 'supplier' and -1.0 or 1.0
            rec.selected_finacial_debt = selected_finacial_debt * sign
            rec.selected_debt = selected_debt * sign
            rec.selected_debt_untaxed = selected_debt_untaxed * sign

    @api.depends(
        'selected_debt', 'unreconciled_amount')
    def _compute_to_pay_amount(self):
        for rec in self:
            rec.to_pay_amount = rec.selected_debt + rec.unreconciled_amount

    @api.onchange('to_pay_amount')
    def _inverse_to_pay_amount(self):
        for rec in self:
            rec.unreconciled_amount = rec.to_pay_amount - rec.selected_debt

    def onchange(self, values, field_name, field_onchange):
        """ Fix this issue https://github.com/ingadhoc/account-payment/issues/189
        """
        fields = []
        for field in field_onchange.keys():
            if field.startswith(('to_pay_move_line_ids.')):
                fields.append(field)
        for field in fields:
            del field_onchange[field]
        return super().onchange(values, field_name, field_onchange)

    @api.onchange('partner_id', 'partner_type', 'company_id')
    def _refresh_payments_and_move_lines(self):
        if self._context.get('to_pay_move_line_ids'):
            return
        for rec in self:
            rec.add_all()

    def _get_to_pay_move_lines_domain(self):
        self.ensure_one()
        return [
            ('partner_id.commercial_partner_id', '=',
                self.commercial_partner_id.id),
            ('account_id.internal_type', '=',
                self.account_internal_type),
            ('account_id.reconcile', '=', True),
            ('reconciled', '=', False),
            ('full_reconcile_id', '=', False),
            ('company_id', '=', self.company_id.id),
            ('move_id.state', '=', 'posted')
            # '|',
            # ('amount_residual', '!=', False),
            # ('amount_residual_currency', '!=', False),
        ]

    def add_all(self):
        for rec in self:
            rec.to_pay_move_line_ids = rec.env['account.move.line'].search(
                rec._get_to_pay_move_lines_domain())

    def remove_all(self):
        self.to_pay_move_line_ids = False

    @api.model
    def default_get(self, defaul_fields):
        # TODO si usamos los move lines esto no haria falta
        rec = super().default_get(defaul_fields)
        rec['payment_date'] = fields.Date.context_today(self)
        to_pay_move_line_ids = self._context.get('to_pay_move_line_ids')
        to_pay_move_lines = self.env['account.move.line'].browse(
            to_pay_move_line_ids).filtered(lambda x: (
                x.account_id.reconcile and
                x.account_id.internal_type in ('receivable', 'payable')))
        if to_pay_move_lines:
            partner = to_pay_move_lines.mapped('partner_id')
            if len(partner) != 1:
                raise ValidationError(_('You can not send to pay lines from different partners'))

            internal_type = to_pay_move_lines.mapped('account_id.internal_type')
            if len(internal_type) != 1:
                raise ValidationError(_('You can not send to pay lines from different partners'))
            rec['partner_id'] = self._context.get('default_partner_id', partner[0].id)
            if internal_type[0] == 'receivable':
                rec['partner_type'] = 'customer'
            else:
                rec['partner_type'] = 'supplier'
            rec['to_pay_move_line_ids'] = [(6, False, to_pay_move_line_ids)]
        return rec

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

    def unreconcile(self):
        self.mapped('payment_ids').unreconcile()
        # TODO en alguos casos setear sent como en payment?
        self.write({'state': 'posted'})

    def cancel(self):
        self.mapped('payment_ids').cancel()
        self.write({'state': 'cancel'})
        return True

    def action_draft(self):
        self.mapped('payment_ids').action_draft()
        # rec.payment_ids.write({'invoice_ids': [(5, 0, 0)]})
        return self.write({'state': 'draft'})

    def unlink(self):
        if any(bool(rec.move_line_ids) for rec in self):
            raise ValidationError(_("You can not delete a payment that is already posted"))
        return super().unlink()

    def confirm(self):
        for rec in self:
            accounts = rec.to_pay_move_line_ids.mapped('account_id')
            if len(accounts) > 1:
                raise ValidationError(_('To Pay Lines must be of the same account!'))
        self.write({'state': 'confirmed'})

    def post(self):
        create_from_website = self._context.get('create_from_website', False)
        create_from_statement = self._context.get('create_from_statement', False)
        create_from_expense = self._context.get('create_from_expense', False)
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
            # if the partner of the payment is different of ht payment group we change it.
            rec.payment_ids.filtered(lambda p : p.partner_id != rec.partner_id).write(
                {'partner_id': rec.partner_id.id})
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
        return True

    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        if self.env.context.get('mark_payment_as_sent'):
            self.filtered(lambda rec: not rec.sent).write({'sent': True})
        return super(AccountPaymentGroup, self.with_context(
            mail_post_autofollow=True)).message_post(**kwargs)

    def action_account_invoice_payment_group(self):
        active_ids = self.env.context.get('active_ids')
        if not active_ids:
            return ''
        move_ids = self.env['account.move'].browse(active_ids)
        if move_ids.filtered(lambda x: x.state != 'posted') or \
                move_ids.filtered(lambda x: x.invoice_payment_state != 'not_paid'):
            raise ValidationError(_('You can only register payment if invoice is posted and unpaid'))
        return {
            'name': _('Register Payment'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.payment.group',
            'view_id': False,
            'target': 'current',
            'type': 'ir.actions.act_window',
            'context': {
                # si bien el partner se puede adivinar desde los apuntes
                # con el default de payment group, preferimos mandar por aca
                # ya que puede ser un contacto y no el commercial partner (y
                # en los apuntes solo hay commercial partner)
                'to_pay_move_line_ids': move_ids.mapped('open_move_line_ids').ids,
                'pop_up': True,
                # We set this because if became from other view and in the
                # context has 'create=False' you can't crate payment lines
                #  (for ej: subscription)
                'create': True,
                'default_company_id': move_ids[0].company_id.id,
            },
        }
