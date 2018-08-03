##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    tax_withholding_id = fields.Many2one(
        'account.tax',
        string='Withholding Tax',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    withholding_number = fields.Char(
        readonly=True,
        states={'draft': [('readonly', False)]},
        help="If you don't set a number we will add a number automatically "
        "from a sequence that should be configured on the Withholding Tax"
    )
    withholding_base_amount = fields.Monetary(
        string='Withholding Base Amount',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )

    @api.multi
    def post(self):
        without_number = self.filtered(
            lambda x: x.tax_withholding_id and not x.withholding_number)

        without_sequence = without_number.filtered(
            lambda x: not x.tax_withholding_id.withholding_sequence_id)
        if without_sequence:
            raise UserError(_(
                'No puede validar pagos con retenciones que no tengan número '
                'de retención. Recomendamos agregar una secuencia a los '
                'impuestos de retención correspondientes. Id de pagos: %s') % (
                without_sequence.ids))

        # a los que tienen secuencia les setamos el numero desde secuencia
        for payment in (without_number - without_sequence):
            payment.withholding_number = \
                payment.tax_withholding_id.withholding_sequence_id.next_by_id()

        return super(AccountPayment, self).post()

    def _get_liquidity_move_line_vals(self, amount):
        vals = super(AccountPayment, self)._get_liquidity_move_line_vals(
            amount)
        if self.payment_method_code == 'withholding':
            if self.payment_type == 'transfer':
                raise UserError(_(
                    'You can not use withholdings on transfers!'))
            if (
                    (self.partner_type == 'customer' and
                        self.payment_type == 'inbound') or
                    (self.partner_type == 'supplier' and
                        self.payment_type == 'outbound')):
                account = self.tax_withholding_id.account_id
            else:
                account = self.tax_withholding_id.refund_account_id
            # if not accounts on taxes then we use accounts of journal
            if account:
                vals['account_id'] = account.id
            vals['name'] = self.withholding_number or '/'
            vals['tax_line_id'] = self.tax_withholding_id.id
            # if not account:
            #     raise UserError(_(
            #         'Accounts not configured on tax %s' % (
            #             self.tax_withholding_id.name)))
        return vals

    @api.multi
    def _compute_payment_method_description(self):
        payments = self.filtered(
            lambda x: x.payment_method_code == 'withholding')
        for rec in payments:
            name = rec.tax_withholding_id.name or rec.payment_method_id.name
            rec.payment_method_description = name
        return super(
            AccountPayment,
            (self - payments))._compute_payment_method_description()
