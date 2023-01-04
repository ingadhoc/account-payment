# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, api, fields, _
from odoo.exceptions import ValidationError, UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    open_move_line_ids = fields.One2many(
        'account.move.line',
        compute='_compute_open_move_lines'
    )
    pay_now_journal_id = fields.Many2one(
        'account.journal',
        'Pay now Journal',
        help='If you set a journal here, after invoice validation, the invoice'
        ' will be automatically paid with this journal. As manual payment'
        'method is used, only journals with manual method are shown.',
        readonly=True,
        states={'draft': [('readonly', False)]},
        # use copy false for two reasons:
        # 1. when making refund it's safer to make pay now empty (specially if automatic refund validation is enable)
        # 2. on duplicating an invoice it's safer also
        copy=False,
    )
    payment_group_ids = fields.Many2many(
        'account.payment.group',
        compute='_compute_payment_groups',
        string='Payment Groups',
        compute_sudo=True,
    )

    payment_group_id = fields.Many2one(
        related='payment_id.payment_group_id',
        store=True,
    )

    @api.constrains('name', 'journal_id', 'state')
    def _check_unique_sequence_number(self):
        payment_group_moves = self.filtered(
            lambda x: x.journal_id.type in ['cash', 'bank'] and x.payment_id.payment_group_id)
        return super(AccountMove, self - payment_group_moves)._check_unique_sequence_number()

    def _compute_payment_groups(self):
        """
        El campo en invoices "payment_id" no lo seteamos con los payment groups
        Por eso tenemos que calcular este campo
        """
        for rec in self:
            rec.payment_group_ids = rec._get_reconciled_payments().mapped('payment_group_id')

    @api.depends('line_ids.account_id.internal_type', 'line_ids.reconciled')
    def _compute_open_move_lines(self):
        for rec in self:
            rec.open_move_line_ids = rec.line_ids.filtered(
                lambda r: not r.reconciled and r.account_id.internal_type in (
                    'payable', 'receivable'))

    def action_register_payment_group(self):
        to_pay_move_lines = self.open_move_line_ids
        if not to_pay_move_lines:
            raise UserError(_('Nothing to be paid on selected entries'))
        to_pay_partners = self.mapped('commercial_partner_id')
        if len(to_pay_partners) > 1:
            raise UserError(_('Selected records must be of the same partner'))

        return {
            'name': _('Register Payment'),
            'view_mode': 'form',
            'res_model': 'account.payment.group',
            'target': 'current',
            'type': 'ir.actions.act_window',
            'context': {
                'default_partner_type': 'customer' if to_pay_move_lines[0].account_id.internal_type == 'receivable' else 'supplier',
                'default_partner_id': to_pay_partners.id,
                'default_to_pay_move_line_ids': to_pay_move_lines.ids,
                # We set this because if became from other view and in the context has 'create=False'
                # you can't crate payment lines (for ej: subscription)
                'create': True,
                'default_company_id': self.company_id.id,
            },
        }

    def action_register_payment(self):
        ''' This method is extended to work like action_register_payment_group() and not like the native odoo method,
        the register payment button will act like the "Registrar Pago" server action '''
        return self.action_register_payment_group()

    def action_post(self):
        res = super(AccountMove, self).action_post()
        self.pay_now()
        return res

    def pay_now(self):
        # validate_payment = not self._context.get('validate_payment')
        for rec in self:
            pay_journal = rec.pay_now_journal_id
            if pay_journal and rec.state == 'posted' and rec.payment_state in ['not_paid', 'patial']:
                # si bien no hace falta mandar el partner_type al paygroup
                # porque el defaults lo calcula solo en funcion al tipo de
                # cuenta, es mas claro mandarlo y podria evitar error si
                # estamos usando cuentas cruzadas (payable, receivable) con
                # tipo de factura
                if rec.move_type in ['in_invoice', 'in_refund']:
                    partner_type = 'supplier'
                else:
                    partner_type = 'customer'

                pay_context = {
                    'default_to_pay_move_line_ids': (rec.open_move_line_ids.ids),
                    'default_company_id': rec.company_id.id,
                    'default_partner_type': partner_type,
                }

                payment_group = rec.env[
                    'account.payment.group'].with_context(
                        pay_context).create({
                            'payment_date': rec.invoice_date,
                            'partner_id': rec.commercial_partner_id.id,
                        })
                # el difference es positivo para facturas (de cliente o
                # proveedor) pero negativo para NC.
                # para factura de proveedor o NC de cliente es outbound
                # para factura de cliente o NC de proveedor es inbound
                # igualmente lo hacemos con el difference y no con el type
                # por las dudas de que facturas en negativo
                if (
                        partner_type == 'supplier' and
                        payment_group.payment_difference >= 0.0 or
                        partner_type == 'customer' and
                        payment_group.payment_difference < 0.0):
                    payment_type = 'outbound'
                    payment_methods = pay_journal.outbound_payment_method_line_ids.payment_method_id
                else:
                    payment_type = 'inbound'
                    payment_methods = pay_journal.inbound_payment_method_line_ids.payment_method_id

                payment_method = payment_methods.filtered(
                    lambda x: x.code == 'manual')
                if not payment_method:
                    raise ValidationError(_(
                        'Pay now journal must have manual method!'))

                payment_group.payment_ids.create({
                    'payment_group_id': payment_group.id,
                    'payment_type': payment_type,
                    'partner_type': partner_type,
                    'company_id': rec.company_id.id,
                    'partner_id': payment_group.partner_id.id,
                    'amount': abs(payment_group.payment_difference),
                    'journal_id': pay_journal.id,
                    'payment_method_id': payment_method.id,
                    'date': rec.invoice_date,
                })
                # if validate_payment:
                payment_group.post()

    def action_view_payment_groups(self):
        if self.move_type in ('in_invoice', 'in_refund'):
            action = self.env.ref('account_payment_group.action_account_payments_group_payable')
        else:
            action = self.env.ref('account_payment_group.action_account_payments_group')

        result = action.sudo().read()[0]

        if len(self.payment_group_ids) != 1:
            result['domain'] = [('id', 'in', self.payment_group_ids.ids)]
        elif len(self.payment_group_ids) == 1:
            res = self.env.ref(
                'account_payment_group.view_account_payment_group_form', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = self.payment_group_ids.id
        return result

    @api.onchange('journal_id')
    def _onchange_journal_reset_pay_now(self):
        # while not always it should be reseted (only if changing company) it's not so usual to set pay now first
        # and then change journal
        self.pay_now_journal_id = False

    def button_draft(self):
        self.filtered(lambda x: x.state == 'posted' and x.pay_now_journal_id).write({'pay_now_journal_id': False})
        return super().button_draft()

    def _get_last_sequence_domain(self, relaxed=False):
        """ para transferencias no queremos que se enumere con el ultimo numero de asiento porque podria ser un
        pago generado por un grupo de pagos y en ese caso el numero viene dado por el talonario de recibo/pago.
        Para esto creamos campo related stored a payment_group_id de manera de que un asiento sepa si fue creado
        o no desde unpaymetn group
        TODO: tal vez lo mejor sea cambiar para no guardar mas numero de recibo en el asiento, pero eso es un cambio
        gigante
        """
        if self.journal_id.type in ('cash', 'bank') and not self.payment_group_id:
            # mandamos en contexto que estamos en esta condicion para poder meternos en el search que ejecuta super
            # y que el pago de referencia que se usa para adivinar el tipo de secuencia sea un pago sin tipo de
            # documento
            where_string, param = super(
                AccountMove, self.with_context(without_payment_group=True))._get_last_sequence_domain(relaxed)
            where_string += " AND payment_group_id is Null"
        else:
            where_string, param = super(AccountMove, self)._get_last_sequence_domain(relaxed)
        return where_string, param

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        if self._context.get('without_payment_group'):
            args += [('payment_group_id', '=', False)]
        return super()._search(args, offset=offset, limit=limit, order=order, count=count, access_rights_uid=access_rights_uid)

    @api.model
    def _deduce_sequence_number_reset(self, name):
        """ Cuando tenemos un move asociado al payment group queremos que el move tenga el mismo nombre que el del payment
        group. Esto para que en cualquier reporte aparezca este nombre de referencia.

        En verion 15 hay una constraint nueva _constrains_date_sequence que trae un problema. cuando vamos a validar un
        account.move revisa el nombre/secuencia que le fue asignado con un regex para encontrar algo parecido a un
        año y lo compara con el año de la fecha del move y si son diferentes años no permite continuar. Ejemplo:
        Tenemos un pago de proveedor que se llama OP - 2022 - 00012345 y lo validamos y generamos los account.move en el
        año 2023. El resultado es que nos salta la excpeción indicando que la secuencia que queremos asignar al move no
        es valida y debe corresponder al año.

        Para fines del account.move no queremos que esto aplique. No importa que nombre utilice el payment.group queremos
        que al validarse se traslade el nombre a los move generados. La modificacion de este metodo logra evitar esa
        comparacion de fechas"""
        if self.payment_group_id:
            return 'never'
        return super()._deduce_sequence_number_reset(name)
