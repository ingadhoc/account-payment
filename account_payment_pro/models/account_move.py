# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, api, Command, fields, _
from odoo.exceptions import UserError


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
        # use copy false for two reasons:
        # 1. when making refund it's safer to make pay now empty (specially if automatic refund validation is enable)
        # 2. on duplicating an invoice it's safer also
        copy=False,
    )

    @api.depends('line_ids.account_id.account_type', 'line_ids.reconciled')
    def _compute_open_move_lines(self):
        for rec in self:
            rec.open_move_line_ids = rec.line_ids.filtered(
                lambda r: not r.reconciled and r.parent_state == 'posted' and
                r.account_id.account_type in self.env['account.payment']._get_valid_payment_account_types())

    def pay_now(self):
        for rec in self.filtered(lambda x: x.pay_now_journal_id and x.state == 'posted' and
                                 x.payment_state in ('not_paid', 'patial')):
            pay_journal = rec.pay_now_journal_id
            if rec.move_type in ['in_invoice', 'in_refund']:
                partner_type = 'supplier'
            else:
                partner_type = 'customer'

            payment_type = 'inbound'
            payment_method = pay_journal._get_manual_payment_method_id(payment_type)

            payment = rec.env[
                'account.payment'].with_context(pay_now=True).create({
                        'date': rec.invoice_date,
                        'partner_id': rec.commercial_partner_id.id,
                        'partner_type': partner_type,
                        'payment_type': payment_type,
                        'company_id': rec.company_id.id,
                        'journal_id': pay_journal.id,
                        'payment_method_id': payment_method.id,
                        'to_pay_move_line_ids': [Command.set(rec.open_move_line_ids.ids)],
                    })

            # el difference es positivo para facturas (de cliente o proveedor) pero negativo para NC.
            # para factura de proveedor o NC de cliente es outbound
            # para factura de cliente o NC de proveedor es inbound
            # igualmente lo hacemos con el difference y no con el type por las dudas de que facturas en negativo
            if (partner_type == 'supplier' and payment.payment_difference >= 0.0 or
               partner_type == 'customer' and payment.payment_difference < 0.0):
                payment.payment_type = 'outbound'
                payment.payment_method_id = pay_journal._get_manual_payment_method_id(payment_type).id
            payment.amount = abs(payment.payment_difference)
            payment.action_post()

    @api.onchange('journal_id')
    def _onchange_journal_reset_pay_now(self):
        # while not always it should be reseted (only if changing company) it's not so usual to set pay now first
        # and then change journal
        self.pay_now_journal_id = False

    def button_draft(self):
        self.filtered(lambda x: x.state == 'posted' and x.pay_now_journal_id).write({'pay_now_journal_id': False})
        return super().button_draft()

    def _post(self, soft=False):
        res = super()._post(soft=soft)
        self.pay_now()
        return res

    def _search_default_journal(self):
        if self.env.context.get('default_company_id'):
            self.env.company =  self.env['res.company'].browse(self.env.context.get('default_company_id'))
        return super()._search_default_journal()
