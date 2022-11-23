##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api


class AccountPayment(models.Model):

    _inherit = "account.payment"

    available_card_ids = fields.Many2many(
        'account.card',
        string='Cards',
        related='payment_method_line_id.available_card_ids'
    )
    card_id = fields.Many2one(
        'account.card',
        string='Card'
    )
    installment_id = fields.Many2one(
        'account.card.installment',
        string='Installment plan'
    )
    tiket_number = fields.Char(
        'Tiket number'
    )
    lot_number = fields.Char(
        'Lot number'
    )
    net_amount = fields.Monetary(
        compute='_computed_net_amount',
        inverse='_inverse_net_amount'
    )

    @api.depends('available_card_ids', 'payment_type')
    @api.onchange('payment_method_line_id')
    def _compute_financing_plan(self):
        with_plan = self.filtered(lambda x: x.payment_type == 'inbound' and x._origin.available_card_ids)
        (self - with_plan).card_id = False
        (self - with_plan).installment_id = False
        for rec in with_plan:
            rec.card_id = rec._origin.available_card_ids[0]

    @api.onchange('card_id')
    def _onchange_card_id(self):
        if len(self.card_id.installment_ids.ids) > 0:
            self.installment_id = self.card_id.installment_ids.ids[0]
        else:
            self.installment_id = False


    @api.depends('amount')
    def _computed_net_amount(self):
        for rec in self:
            rec.net_amount = rec.amount / (rec.installment_id.surcharge_coefficient or 1)

    @api.onchange('installment_id')
    def _onchange_instalment(self):
        """ no agregamos este onchange en el de _inverse_net_amount porque si no el amount se inicializa en cero.
        Eventualmente habria que mejorar esto. Se podria tal vez pasar el default por vista al net_amount tmb """
        for rec in self:
            rec._inverse_net_amount()

    def _inverse_net_amount(self):
        for rec in self:
            rec.with_context(skip_account_move_synchronization=True).amount = rec.net_amount * (rec.installment_id.surcharge_coefficient or 1)

    @api.model
    def default_get(self, default_fields):
        if self._context.get('open_invoice_payment', False):
            self = self.with_context(active_ids=None, active_model=None)
        return super().default_get(default_fields)

    @api.onchange('payment_group_id')
    def onchange_payment_group_id(self):
        payment_diff = self.payment_group_id.payment_difference
        super().onchange_payment_group_id()
        if self.payment_group_id and self.payment_group_id.financing_surcharge:
            self.amount = payment_diff + self.payment_group_id.financing_surcharge
