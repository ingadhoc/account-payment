##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    available_pop_session_ids = fields.Many2many('pop.session',
        string='Active Session',
        compute='_compute_available_pop_session_ids',
    )
    pop_session_id = fields.Many2one('pop.session',
        string='Session',
        compute="_compute_pop_session_id",
        readonly=True,
        store=True
    )
    pop_id = fields.Many2one('pop.config',
        string='POP config',
        related='pop_session_id.pop_id'
    )
    dest_pop_id = fields.Many2one('pop.config',
        string='Destination POP config',
    )

    def _compute_pop_session_id(self):
        for rec in self:
            session_ids = self.env['pop.session'].search([
                ('user_ids', '=', self.env.uid),
                ('state', '=', 'opened')
            ])
            if len(session_ids) == 1:
                rec.pop_session_id = session_ids.id
            else:
                rec.pop_session_id = False

    def _update_pop_session_id(self):
        for rec in self.filtered(lambda s: s.pop_session_id and s.state=='draft'):
            session_ids = self.env['pop.session'].search([
                ('user_ids', '=', self.env.uid),
                ('state', '=', 'opened'),
                ('pop_id', '=', rec.pop_session_id.pop_id.id)
            ])
            if len(session_ids) == 1:
                rec.pop_session_id = session_ids.id
            else:
                rec.pop_session_id = False

    @api.constrains('journal_id', 'currency_id')
    def check_journal_currency(self):
        for payment in self:
            if payment.journal_id.currency_id and payment.currency_id != payment.journal_id.currency_id:
                raise ValidationError(
                    _('The currency of the journal must be the of the payment.'))

    def action_receive_internal_transaction(self):
        pop_ids = self.env['pop.session'].search([
            ('user_ids', '=', self.env.uid),
            ('state', '=', 'opened')
        ]).mapped('pop_id')
        for rec in self.filtered(lambda p: p.dest_pop_id == pop_ids and p.dest_pop_session_id == False):
            rec.dest_pop_session_id = rec.dest_pop_id.current_session_id.id

    @api.depends('payment_type', 'company_id')
    def _compute_available_pop_session_ids(self):
        session_ids = self.env['pop.session'].search([
            ('user_ids', '=', self.env.uid),
            ('state', '=', 'opened')
        ])
        for rec in self:
            rec.available_pop_session_ids = session_ids

    def action_post(self):
        require_session = self.env.user.requiere_pos_session
        for rec in self:
            if  self.pop_session_id.state != 'opened':
                raise UserError(_('Open payment session is required'))

            if not rec.pop_session_id or rec.pop_session_id not in rec.available_pop_session_ids:
                if require_session and not rec.available_pop_session_ids:
                    raise UserError(_('Open payment session is required for your user'))

        super().action_post()

    def action_cancel(self):
        # require_session = self.env.user.requiere_pos_session
        # session_id = self.env['pop.session'].search([
        #     ('user_ids', '=', self.env.uid),
        #     ('state', '=', 'opened')
        # ])
        # if require_session and not session_id:
        #     raise UserError(_('Open payment session is required for your user'))
        # # TODO: Ver

        super().action_cancel()

    @api.depends('payment_type','pop_session_id')
    def _compute_available_journal_ids(self):

        if self.pop_session_id:
            """
            Get all journals having at least one payment method for inbound/outbound depending on the payment_type.
            """
            journals = self.env['account.journal'].search([
                ('company_id', 'in', self.company_id.ids), ('type', 'in', ('bank', 'cash')),('id', 'in', self.pop_session_id.journal_ids.ids)
            ])
            for pay in self:
                if pay.payment_type == 'inbound':
                    pay.available_journal_ids = journals.filtered(
                        lambda j: j.company_id == pay.company_id and j.inbound_payment_method_line_ids.ids != []
                    )
                else:
                    pay.available_journal_ids = journals.filtered(
                        lambda j: j.company_id == pay.company_id and j.outbound_payment_method_line_ids.ids != []
                    )
        else:
            super()._compute_available_journal_ids()


    def _create_paired_internal_transfer_payment(self):

        pop_transfer =  self.filtered('dest_pop_id')
        super(AccountPayment, self - pop_transfer)._create_paired_internal_transfer_payment()

        for payment in pop_transfer:

            paired_payment = payment.copy({
                'journal_id': payment.journal_id.id,
                'destination_journal_id': payment.journal_id.id,
                'payment_type': payment.payment_type == 'outbound' and 'inbound' or 'outbound',
                'move_id': None,
                'ref': payment.ref,
                'paired_internal_transfer_payment_id': payment.id,
                'date': payment.date,
            })
            paired_payment.move_id._post(soft=False)
            payment.paired_internal_transfer_payment_id = paired_payment

            body = _(
                "This payment has been created from %s",
                payment._get_html_link(),
            )
            paired_payment.message_post(body=body)
            body = _(
                "A second payment has been created: %s",
                paired_payment._get_html_link(),
            )
            payment.message_post(body=body)

            lines = (payment.move_id.line_ids + paired_payment.move_id.line_ids).filtered(
                lambda l: l.account_id == payment.destination_account_id and not l.reconciled)
            lines.reconcile()


