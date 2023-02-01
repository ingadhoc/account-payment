##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime


class AccountPaymentRegister(models.TransientModel):

    _inherit = 'account.payment.register'

    available_pop_session_ids = fields.Many2many('pop.session',
        string='Active Session',
        compute='_compute_available_pop_session_ids',
    )
    pop_session_id = fields.Many2one('pop.session',
        string='Session',
    )
    pop_id = fields.Many2one('pop.config',
        string='POP config',
        related='pop_session_id.pop_id'
    )

    @api.depends('payment_type', 'company_id', 'can_edit_wizard')
    def _compute_available_pop_session_ids(self):
        session_ids = self.env['pop.session'].search([
            ('user_ids', '=', self.env.uid),
            ('state', '=', 'opened')
        ])
        for rec in self:
            rec.available_pop_session_ids = session_ids
            if session_ids and not rec.pop_session_id:
                rec.pop_session_id= session_ids[0].id

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

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.pop_session_id:
            payment_vals['pop_session_id'] = self.pop_session_id.id
        return payment_vals

    def _create_payment_vals_from_batch(self, batch_result):
        payment_vals = super()._create_payment_vals_from_batch(batch_result)
        if self.pop_session_id:
            payment_vals['pop_session_id'] = self.pop_session_id.id
        return payment_vals
