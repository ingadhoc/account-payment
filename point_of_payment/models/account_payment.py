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
        #ondelete='Restrict',
    )
    pop_id = fields.Many2one('pop.config',
        string='POP config',
        #ondelete='Restrict',
        related='pop_session_id.pop_id'
    )

    @api.depends('payment_type', 'company_id')
    def _compute_available_pop_session_ids(self):
        session_ids = self.env['pop.session'].search([
            ('user_ids', '=', self.env.uid),
            ('state', '=', 'opened')
        ])
        for rec in self:
            rec.available_pop_session_ids = session_ids

    def action_post(self):
        require_session = self.env.user.has_group('point_of_payment.require_pop_session')
        for rec in self:
            if not rec.pop_session_id or rec.pop_session_id not in rec.available_pop_session_ids:
                session_id = rec.available_pop_session_ids[0]
                if require_session and not session_id:
                    raise UserError(_('Open payment session is required for your user'))

                rec.pop_session_id = session_id.id  if session_id else False
        super().action_post()

    def action_cancel(self):
        # require_session = self.env.user.has_group('point_of_payment.require_pop_session')
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
