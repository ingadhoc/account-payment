# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api
# from odoo.exceptions import UserError, ValidationError


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # inverse field of the one created on payment groups, used by other modules
    # like sipreco
    payment_group_ids = fields.Many2many(
        'account.payment.group',
        'account_move_line_payment_group_to_pay_rel',
        'to_pay_line_id',
        'payment_group_id',
        string="Payment Groups",
        readonly=True,
        copy=False,
        # auto_join not yet implemented for m2m. TODO enable when implemented
        # https://github.com/odoo/odoo/blob/master/odoo/osv/expression.py#L899
        # auto_join=True,
    )

    @api.depends_context('payment_group_id')
    def _compute_payment_group_matched_amount(self):
        """
        Reciviendo un payment_group_id por contexto, decimos en ese payment
        group, cuanto se pago para la lína en cuestión.
        """
        payment_group_id = self._context.get('payment_group_id')
        if not payment_group_id:
            self.payment_group_matched_amount = 0.0
            return False
        payments = self.env['account.payment.group'].browse(payment_group_id).payment_ids
        payment_lines = payments.mapped('move_line_ids').filtered(lambda x: x.account_internal_type in ['receivable', 'payable'])

        for rec in self:
            debit_move_amount = sum(payment_lines.mapped('matched_debit_ids').filtered(lambda x: x.debit_move_id == rec).mapped('amount'))
            credit_move_amount = sum(payment_lines.mapped('matched_credit_ids').filtered(lambda x: x.credit_move_id == rec).mapped('amount'))
            rec.payment_group_matched_amount = debit_move_amount - credit_move_amount

    payment_group_matched_amount = fields.Monetary(
        compute='_compute_payment_group_matched_amount',
        currency_field='company_currency_id',
    )
