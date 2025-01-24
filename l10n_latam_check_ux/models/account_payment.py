from odoo import models, api
from odoo.exceptions import ValidationError


class AccountPayment(models.Model):
    _inherit = 'account.payment'


    def action_post(self):
        # nosotros queremos bloquear tmb nros de cheques de terceros que sea unicos
        # para esto chequeamos el campo computado de warnings que ya lo tiene incorporado
        # NOTA: no mandamos todos los warnings de "self" juntos porque podría ser muy verbose (por ej. la
        # leyenda de cheques duplicados en un mismo payment group apareceria varias veces si el cheque está repetido
        # en el mismo payment group)
        for rec in self:
            if rec.l10n_latam_check_warning_msg:
                raise ValidationError('%s' % rec.l10n_latam_check_warning_msg)
        super().action_post()
