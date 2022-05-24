##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, _
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

    def _get_valid_liquidity_accounts(self):
        res = super()._get_valid_liquidity_accounts()
        if self.tax_withholding_id:
            res += (self._get_withholding_repartition_line().account_id,)

        return res

    def action_post(self):
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

        return super(AccountPayment, self).action_post()

    def _get_withholding_repartition_line(self):
        self.ensure_one()
        if ((self.partner_type == 'customer' and self.payment_type == 'inbound') or
                (self.partner_type == 'supplier' and self.payment_type == 'outbound')):
            rep_field = 'invoice_repartition_line_ids'
        else:
            rep_field = 'refund_repartition_line_ids'
        rep_line = self.tax_withholding_id[rep_field].filtered(lambda x: x.repartition_type == 'tax')
        if len(rep_line) != 1:
            raise UserError(
                'En los impuestos de retención debe haber una línea de repartición de tipo tax para pagos y otra'
                'para reembolsos')
        if not rep_line.account_id:
            raise UserError(_('The tax %s dont have account configured on the tax repartition line') % (
                rep_line.tax_id.name))
        return rep_line

    def _prepare_move_line_default_vals(self, write_off_line_vals=None):
        res = super()._prepare_move_line_default_vals(write_off_line_vals=write_off_line_vals)

        if self.payment_method_code == 'withholding':
            if self.payment_type == 'transfer':
                raise UserError(_('You can not use withholdings on transfers!'))
            rep_line = self._get_withholding_repartition_line()
            res[0]['name'] = self.withholding_number or '/'
            res[0]['account_id'] = rep_line.account_id.id
            res[0]['tax_repartition_line_id'] = rep_line.id
        return res
