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

    def _get_valid_liquidity_accounts(self):
        res = super()._get_valid_liquidity_accounts()
        if self.tax_withholding_id:
            # si es un withholding payment entonces la cuenta de liquidez puede ser cualquier cuenta utilizda en una
            # repatition line ya que podemos estar cambiando de impuesto (y al llegar a este paso no sabemos el
            # impuesto anterior) o estar cambiando entre rep line "invoice y refund". De hecho deberiamos ser hasta
            # mas permisivos (tal vez assets account con reconcile = False? solo para este caso de withholding payment?)
            # igual asi por ahora estamos y en 17 esto se depreciaria
            rep_lines = self.env['account.tax.repartition.line'].search(
                [('company_id', '=', self.company_id.id), '|',
                    ('invoice_tax_id.type_tax_use', 'in', ['supplier', 'customer']),
                    ('refund_tax_id.type_tax_use', 'in', ['supplier', 'customer'])])
            res += tuple(rep_lines.mapped('account_id'))

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

        # en los apuntes de retenciones necesitamos que quede tax_line_id vinculado para poder hacer liquidaciones
        # de impuestos. Anteriormente pasabamos el tax_repartition_line_id en _prepare_move_line_default_vals
        # pero ahora nos da un error porque _sync_unbalanced_lines hace line_ids.filtered('tax_line_id').unlink()
        # y termina modificando el asiento. El cambio anterior funcionaba en algunos casos pero no en otros.
        # Hacemos este parche feo total deberia ser solo por v16 ya que en v17 lo pondriamos nativo en odoo.
        # Basicamente escribimos el dato luego de validar el payment (lo escribimos con ._write porque write hace
        # unos chequeos y resetea). Ademas luego al pasar a borrador limpiamos el dato para no tener el mismo error.
        res = super(AccountPayment, self).action_post()
        withholdings = self.filtered(lambda x: x.tax_withholding_id)
        for withholding in withholdings:
            liquidity_lines, counterpart_lines, writeoff_lines = withholding._seek_for_lines()
            rep_line = withholding._get_withholding_repartition_line()
            liquidity_lines.tax_repartition_line_id = rep_line
            liquidity_lines.tax_line_id = rep_line.tax_id
        return res

    def action_draft(self):
        ''' posted -> draft '''
        withholdings = self.filtered(lambda x: x.tax_withholding_id)
        for withholding in withholdings:
            # no podemos llamar a action_draft sin hacer esto porque action_draft termina llamando a
            # move_id.button_draft y eso genera recomputo de lineas porque hay tax_ids involucrados. Es recomputo
            # genera cambios no compatibles con un pago.
            # por eso antes de llamar a super tenemos que borrar toda la info de impuestos
            liquidity_lines, counterpart_lines, writeoff_lines = withholding._seek_for_lines()
            # antes de poder hacer el write hacemos este hack para poder pasar esta constraint
            # https://github.com/odoo/odoo/blob/b03d4c643647/addons/account/models/account_move_line.py#L1416
            liquidity_lines.parent_state = 'draft'
            liquidity_lines.write({
                'tax_repartition_line_id': False,
                'tax_line_id': False,
            })
        return super().action_draft()

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
        return res

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        res = super()._get_trigger_fields_to_synchronize()
        return res + ('withholding_number', 'tax_withholding_id')
