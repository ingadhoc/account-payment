# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import logging
_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    counterpart_currency_amount = fields.Monetary(currency_field='counterpart_currency_id')
    counterpart_currency_id = fields.Many2one('res.currency')

    def _prepare_move_line_default_vals(self, write_off_line_vals=None):
        res = super()._prepare_move_line_default_vals(write_off_line_vals=write_off_line_vals)
        if self.counterpart_currency_id and self.currency_id == self.company_id.currency_id and self.counterpart_currency_id != self.currency_id:
            # counterpart_amount_currency = -liquidity_amount_currency - write_off_amount_currency
            write_off_line_vals_list = write_off_line_vals or []
            write_off_amount_currency = sum(x['amount_currency'] for x in write_off_line_vals_list)
            if write_off_amount_currency:
                raise ValidationError('No se puede forzar moneda de contrapartida si hay ajustes')
            if self.payment_type == 'inbound':
                # Receive money.
                liquidity_amount_currency = self.counterpart_currency_amount
            elif self.payment_type == 'outbound':
                # Send money.
                liquidity_amount_currency = -self.counterpart_currency_amount
            res[1].update({
                'currency_id': self.counterpart_currency_id.id,
                'amount_currency': -liquidity_amount_currency
            })
        return res

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        res = super()._get_trigger_fields_to_synchronize()
        # si bien es un metodo api.model usamos este hack para chequear si es la creacion de un payment que termina
        # triggereando un write y luego llamando a este metodo y dando error, por ahora no encontramos una mejor forma
        # esto esta ligado de alguna manera a un llamado que se hace dos veces por "culpa" del método
        # "_inverse_amount_company_currency". Si bien no es elegante para todas las pruebas que hicimos funcionó bien.
        # IMPORTANTE copiamos el if de caso similar con force_amount_company_currency pero no verificamos si aca tmb
        # era necesario
        if self.mapped('open_move_line_ids'):
            return res + ('counterpart_currency_amount', 'counterpart_currency_id')
        return res
