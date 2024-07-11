# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, api, fields, _
from odoo.exceptions import ValidationError


class AccountPaymentGroup(models.Model):
    _name = "account.payment.group"
    _description = "Payment Group"
    _order = "payment_date desc, name desc"
    _inherit = 'mail.thread'
    _check_company_auto = True

    name = fields.Char(string='Number', readonly=True, copy=False)
    document_sequence_id = fields.Many2one(
        related='receiptbook_id.sequence_id',
    )
    receiptbook_id = fields.Many2one(
        'account.payment.receiptbook',
        'ReceiptBook',
        readonly=True,
        states={'draft': [('readonly', False)]},
        auto_join=True,
        check_company=True,
        compute='_compute_receiptbook',
        store=True,
    )
    document_type_id = fields.Many2one(
        related='receiptbook_id.document_type_id',
    )
    next_number = fields.Integer(
        # related='receiptbook_id.sequence_id.number_next_actual',
        compute='_compute_next_number',
        string='Next Number',
    )
    document_number = fields.Char(
        compute='_compute_document_number', inverse='_inverse_document_number',
        string='Document Number', readonly=True, states={'draft': [('readonly', False)]})
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
        tracking=True,
        change_default=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        tracking=True,
        change_default=True,
        index=True,
        check_company=True,
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
        tracking=True,
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
    selected_debt = fields.Monetary(
        # string='To Pay lines Amount',
        string='Selected Debt',
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
        tracking=True,
    )
    payments_amount = fields.Monetary(
        compute='_compute_payments_amount',
        string='Amount',
        tracking=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
    ],
        readonly=True,
        default='draft',
        copy=False,
        string="Status",
        tracking=True,
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
        compute='_compute_to_pay_move_lines', store=True,
        help='This lines are the ones the user has selected to be paid.',
        copy=False,
        readonly=True,
        states={'draft': [('readonly', False)]},
        check_company=True
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
    payment_difference = fields.Monetary(
        compute='_compute_payment_difference',
        readonly=True,
        string="Payments Difference",
        help="Difference between selected debt (or to pay amount) and "
        "payments amount"
    )
    payment_ids = fields.One2many(
        'account.payment',
        'payment_group_id',
        string='Payment Lines',
        copy=False,
        readonly=True,
        states={
            'draft': [('readonly', False)],
            'confirmed': [('readonly', False)]},
        auto_join=True,
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

    _sql_constraints = [
        ('name_uniq', 'unique(name, receiptbook_id)',
            'Document number must be unique per receiptbook!')]

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

    @api.depends('payment_ids.line_ids')
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
            payment_lines = rec.payment_ids.mapped('line_ids').filtered(lambda x: x.account_internal_type in ['receivable', 'payable'])
            debit_moves = payment_lines.mapped('matched_debit_ids.debit_move_id')
            credit_moves = payment_lines.mapped('matched_credit_ids.credit_move_id')
            debit_lines_sorted = debit_moves.filtered(lambda x: x.date_maturity != False).sorted(key=lambda x: (x.date_maturity, x.move_id.name))
            credit_lines_sorted = credit_moves.filtered(lambda x: x.date_maturity != False).sorted(key=lambda x: (x.date_maturity, x.move_id.name))
            debit_lines_without_date_maturity = debit_moves - debit_lines_sorted
            credit_lines_without_date_maturity = credit_moves - credit_lines_sorted
            rec.matched_move_line_ids =  ((debit_lines_sorted + debit_lines_without_date_maturity) | (credit_lines_sorted + credit_lines_without_date_maturity)) - payment_lines

    @api.depends('payment_ids.line_ids')
    def _compute_move_lines(self):
        for rec in self:
            rec.move_line_ids = rec.payment_ids.mapped('line_ids')

    @api.depends('to_pay_amount', 'payments_amount')
    def _compute_payment_difference(self):
        for rec in self:
            # if rec.payment_subtype != 'double_validation':
            #     continue
            rec.payment_difference = rec.to_pay_amount - rec.payments_amount

    @api.depends('payment_ids.l10n_ar_amount_company_currency_signed')
    def _compute_payments_amount(self):
        for rec in self:
            # this hac is to make it work when creating payment groups with payments without saving + saved records
            rec.payments_amount = sum((rec._origin.payment_ids + rec.payment_ids.filtered(lambda x: not x.ids)).mapped(
                'l10n_ar_amount_company_currency_signed'))

    @api.depends('to_pay_move_line_ids.amount_residual')
    def _compute_selected_debt(self):
        for rec in self:
            rec.selected_debt = sum(rec.to_pay_move_line_ids._origin.mapped('amount_residual')) * (-1.0 if rec.partner_type == 'supplier' else 1.0)

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
        for rec in self:
            rec.add_all()

    def _get_to_pay_move_lines_domain(self):
        self.ensure_one()
        return [
            ('partner_id.commercial_partner_id', '=', self.commercial_partner_id.id),
            ('company_id', '=', self.company_id.id), ('move_id.state', '=', 'posted'),
            ('account_id.reconcile', '=', True), ('reconciled', '=', False), ('full_reconcile_id', '=', False),
            ('account_id.internal_type', '=', 'receivable' if self.partner_type == 'customer' else 'payable'),
        ]

    def add_all(self):
        for rec in self:
            rec.to_pay_move_line_ids = rec.env['account.move.line'].search(
                rec._get_to_pay_move_lines_domain())

    def remove_all(self):
        self.to_pay_move_line_ids = False

    @api.model
    def default_get(self, defaul_fields):
        res = super().default_get(defaul_fields)
        if not res.get('payment_date'):
            res['payment_date'] = fields.Date.context_today(self)
        return res

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

    def cancel(self):
        self.mapped('payment_ids').action_cancel()
        self.write({'state': 'cancel'})
        return True

    def action_draft(self):
        self.mapped('payment_ids').action_draft()
        return self.write({'state': 'draft'})

    @api.ondelete(at_uninstall=False)
    def _unlink_if_not_posted(self):
        recs = self.filtered(lambda x: x.state == 'posted')
        if recs:
            raise ValidationError(_('You can not delete posted payment groups. Payment group ids: %s') % recs.ids)

    def unlink(self):
        """ Hacemos unlink de esta manera y no con el ondelete cascade porque con este ultimo se hace eliminacion
        por sql y no se llama el metodo unlin de odoo account.payment que se encarga de propagar la eliminacion al
        account.move"""
        payments = self.mapped('payment_ids')
        res = super().unlink()
        payments.unlink()
        return res

    def confirm(self):
        for rec in self:
            accounts = rec.to_pay_move_line_ids.mapped('account_id')
            if len(accounts) > 1:
                raise ValidationError(_('To Pay Lines must be of the same account!'))
        self.write({'state': 'confirmed'})

    def post(self):
        """ Post payment group. If payment is created automatically when creating a payment (for eg. from website
        or expenses), then:
        1. do not post payments (posted by super method)
        2. do not reconcile (reconciled by super)
        3. do not check double validation
        TODO: may be we can improve code and actually do what we want for payments from payment groups"""
        created_automatically = self._context.get('created_automatically')
        posted_payment_groups = self.filtered(lambda x: x.state == 'posted')
        if posted_payment_groups:
            raise ValidationError(_(
                "You can't post and already posted payment group. Payment group ids: %s") % posted_payment_groups.ids)
        for rec in self:
            if not rec.document_number:
                if rec.receiptbook_id and not rec.receiptbook_id.sequence_id:
                    raise ValidationError(_(
                        'Error!. Please define sequence on the receiptbook'
                        ' related documents to this payment or set the '
                        'document number.'))
                if rec.receiptbook_id.sequence_id:
                    rec.document_number = (
                        rec.receiptbook_id.with_context(
                            ir_sequence_date=rec.payment_date
                        ).sequence_id.next_by_id())
            # por ahora solo lo usamos en _get_last_sequence_domain para saber si viene de una transferencia (sin
            # documen type) o es de un grupo de pagos. Pero mas alla de eso no tiene un gran uso, viene un poco legacy
            # y ya está configurado en los receibooks
            rec.payment_ids.l10n_latam_document_type_id = rec.document_type_id.id

            if not rec.payment_ids:
                raise ValidationError(_(
                    'You can not confirm a payment group without payment lines!'))
            # si todos los pagos hijos estan posteados es probable que venga de un pago creado en otro lugar
            # (expenses por ejemplo), en ese caso salteamos la dobule validation
            if (rec.payment_subtype == 'double_validation' and rec.payment_difference and not created_automatically):
                raise ValidationError(_('To Pay Amount and Payment Amount must be equal!'))

            # if the partner of the payment is different of ht payment group we change it.
            rec.payment_ids.filtered(lambda p: p.partner_id != rec.partner_id.commercial_partner_id).write(
                {'partner_id': rec.partner_id.commercial_partner_id.id})

            # no volvemos a postear lo que estaba posteado
            if not created_automatically:
                rec.payment_ids.filtered(lambda x: x.state == 'draft').action_post()
            # escribimos despues del post para que odoo no renumere el payment
            rec.payment_ids.name = rec.name

            if not rec.receiptbook_id and not rec.name:
                rec.name = any(
                    rec.payment_ids.mapped('name')) and ', '.join(
                    rec.payment_ids.mapped('name')) or False

            if not created_automatically:
                counterpart_aml = rec.payment_ids.mapped('line_ids').filtered(
                    lambda r: not r.reconciled and r.account_id.internal_type in ('payable', 'receivable'))
                if counterpart_aml and rec.to_pay_move_line_ids:
                    (counterpart_aml + (rec.to_pay_move_line_ids)).reconcile()

            rec.state = 'posted'

            if rec.receiptbook_id.mail_template_id:
                rec.message_post_with_template(rec.receiptbook_id.mail_template_id.id)
        return True

    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        if self.env.context.get('mark_payment_as_sent'):
            self.filtered(lambda rec: not rec.sent).write({'sent': True})
        return super(AccountPaymentGroup, self.with_context(
            mail_post_autofollow=True)).message_post(**kwargs)

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

    # from old account_payment_document_number

    @api.depends('name')
    def _compute_document_number(self):
        recs_with_name = self.filtered('name')
        for rec in recs_with_name:
            name = rec.name
            doc_code_prefix = rec.document_type_id.doc_code_prefix
            if doc_code_prefix and name:
                name = name.split(" ", 1)[-1]
            rec.document_number = name
        remaining = self - recs_with_name
        remaining.document_number = False

    @api.onchange('document_type_id', 'document_number')
    def _inverse_document_number(self):
        for rec in self.filtered('document_type_id'):
            if not rec.document_number:
                rec.name = False
            else:
                document_number = rec.document_type_id._format_document_number(rec.document_number)
                if rec.document_number != document_number:
                    rec.document_number = document_number
                rec.name = "%s %s" % (rec.document_type_id.doc_code_prefix, document_number)

    @api.depends(
        'receiptbook_id.sequence_id.number_next_actual',
    )
    def _compute_next_number(self):
        """
        show next number only for payments without number and on draft state
        """
        for payment in self:
            if payment.state != 'draft' or not payment.receiptbook_id or payment.document_number:
                payment.next_number = False
                continue
            sequence = payment.receiptbook_id.sequence_id
            # we must check if sequence use date ranges
            if not sequence.use_date_range:
                payment.next_number = sequence.number_next_actual
            else:
                dt = self.payment_date or fields.Date.today()
                seq_date = self.env['ir.sequence.date_range'].search([
                    ('sequence_id', '=', sequence.id),
                    ('date_from', '<=', dt),
                    ('date_to', '>=', dt)], limit=1)
                if not seq_date:
                    seq_date = sequence._create_date_range_seq(dt)
                payment.next_number = seq_date.number_next_actual

    @api.depends('company_id', 'partner_type')
    def _compute_receiptbook(self):
        for rec in self.filtered(lambda x: not x.receiptbook_id or x.receiptbook_id.company_id != x.company_id):
            partner_type = self.partner_type or self._context.get(
                'partner_type', self._context.get('default_partner_type', False))
            receiptbook = self.env[
                'account.payment.receiptbook'].search([
                    ('partner_type', '=', partner_type),
                    ('company_id', '=', self.company_id.id),
                ], limit=1)
            rec.receiptbook_id = receiptbook
