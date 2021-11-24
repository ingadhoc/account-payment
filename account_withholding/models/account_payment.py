##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountPaymentMethodAW(models.Model):
    _inherit = 'account.payment.method'

    @api.model
    def _get_payment_method_information(self):
        res = super(AccountPaymentMethodAW, self)._get_payment_method_information()
        res['withholding_in'] =  {'mode': 'multi', 'domain': [('type', 'in', ('bank', 'cash'))]}
        res['withholding_out'] = {'mode': 'multi', 'domain': [('type', 'in', ('bank', 'cash'))]}
        return res


class AccountPaymentAW(models.Model):
    _inherit = "account.payment"

    tax_withholding_id = fields.Many2one(
        'account.tax',
        string='Withholding Tax',
        #readonly=True,
        states={'draft': [('readonly', False)]},
    )
    withholding_number = fields.Char(
        #readonly=True,
        states={'draft': [('readonly', False)]},
        help="If you don't set a number we will add a number automatically "
        "from a sequence that should be configured on the Withholding Tax"
    )
    withholding_base_amount = fields.Monetary(
        string='Withholding Base Amount',
        #readonly=True,
        states={'draft': [('readonly', False)]},
    )

    payment_method_code = fields.Char(related='payment_method_line_id.code')


    def _prepare_move_line_default_vals(self, write_off_line_vals=None):
        vals = super(AccountPaymentAW, self)._prepare_move_line_default_vals(write_off_line_vals=write_off_line_vals)
        for move_line_vals in vals:
            move_line_vals.update(self._get_withholding_line_vals())
        return vals

    """
    def _prepare_payment_moves(self):
        all_moves_vals = []
        for rec in self:
            moves_vals = super(AccountPaymentRegister, rec)._prepare_payment_moves()

            vals = rec._get_withholding_line_vals()
            if vals:
                moves_vals[0]['line_ids'][1][2].update(vals)

            all_moves_vals += moves_vals

        return all_moves_vals
    """


    def _get_withholding_line_vals(self):
        vals = {}
        if self.payment_method_code in ['withholding_in', 'withholding_out']:
            if self.payment_type == 'transfer':
                raise UserError(_(
                    'You can not use withholdings on transfers!'))
            if (
                    (self.partner_type == 'customer' and
                        self.payment_type == 'inbound') or
                    (self.partner_type == 'supplier' and
                        self.payment_type == 'outbound')):
                rep_field = 'invoice_repartition_line_ids'
            else:
                rep_field = 'refund_repartition_line_ids'
            rep_lines = self.tax_withholding_id[rep_field].filtered(lambda x: x.repartition_type == 'tax')
            if len(rep_lines) != 1:
                raise UserError(
                    'En los impuestos de retención debe haber una línea de repartición de tipo tax para pagos y otra'
                    'para reembolsos')
            account = rep_lines.account_id
            # if not accounts on taxes then we use accounts of journal
            if account:
                vals['account_id'] = account.id
            vals['name'] = self.withholding_number or '/'
            vals['tax_repartition_line_id'] = rep_lines.id
            # if not account:
            #     raise UserError(_(
            #         'Accounts not configured on tax %s' % (
            #             self.tax_withholding_id.name)))
        return vals

    @api.depends('payment_method_code', 'tax_withholding_id.name')
    def _compute_payment_method_description(self):
        payments = self.filtered(
            lambda x: x.payment_method_code in ['withholding_in', 'withholding_out'])
        for rec in payments:
            name = rec.tax_withholding_id.name or rec.payment_method_id.name
            rec.payment_method_description = name
        return super(AccountPaymentAW, self)._compute_payment_method_description()

class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    tax_withholding_id = fields.Many2one(
        'account.tax',
        string='Withholding Tax',
        #readonly=True,
        states={'draft': [('readonly', False)]},
    )
    withholding_number = fields.Char(
        #readonly=True,
        states={'draft': [('readonly', False)]},
        help="If you don't set a number we will add a number automatically "
        "from a sequence that should be configured on the Withholding Tax"
    )
    withholding_base_amount = fields.Monetary(
        string='Withholding Base Amount',
        #readonly=True,
        states={'draft': [('readonly', False)]},
    )

    type_tax_use = fields.Selection(related='tax_withholding_id.type_tax_use')

    payment_method_code = fields.Char(related='payment_method_line_id.code')

    def _create_payment_vals_from_batch(self, batch_result):
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

        res = super(AccountPaymentRegister, self)._create_payment_vals_from_batch(batch_result)
        res.update({
            'tax_withholding_id': self.tax_withholding_id.id,
            'withholding_number' : self.withholding_number,
            'withholding_base_amount': self.withholding_base_amount,
        })
        return res

    @api.depends('payment_method_code', 'tax_withholding_id.name')
    def _compute_payment_method_description(self):
        payments = self.filtered(
            lambda x: x.payment_method_code in ['withholding_in', 'withholding_out'])
        for rec in payments:
            name = rec.tax_withholding_id.name or rec.payment_method_id.name
            rec.payment_method_description = name
        return super(AccountPaymentRegister, self)._compute_payment_method_description()
