# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, api


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    @api.multi
    def register_payment(
            self, payment_line,
            writeoff_acc_id=False, writeoff_journal_id=False):
        """
        Con esto arreglamos que los pagos puedan pagar contra una cuenta
        no conciliable, arreglamos porque odoo manda a conciliar por mas
        que no haya facturas y da error, entonces si no hay facturas
        que no intente conciliar nada (lo usamos en sipreco esto por ej)
        """
        if not self:
            return True
        return super(AccountInvoice, self).register_payment(
            payment_line, writeoff_acc_id=writeoff_acc_id,
            writeoff_journal_id=writeoff_journal_id)
