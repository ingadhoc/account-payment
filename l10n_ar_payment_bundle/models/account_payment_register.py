from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    """
    Filtramos el diario de bundle (paquete de pagos) de los diarios disponibles
    en el asistente de pagos cuando la compañía no usa Payment Pro, para evitar
    que se seleccione manualmente un diario que debe usarse solo desde el formulario.
    """

    _inherit = "account.payment.register"

    use_payment_pro = fields.Boolean(compute="_compute_use_payment_pro")

    def _compute_use_payment_pro(self):
        payment_with_pro = self.filtered(
            lambda x: x.company_id.use_payment_pro and x.payment_method_line_id.payment_account_id
        )
        payment_with_pro.use_payment_pro = True
        (self - payment_with_pro).use_payment_pro = False

    @api.depends("available_journal_ids", "company_id")
    def _compute_available_journal_ids(self):
        super()._compute_available_journal_ids()
        for rec in self.filtered(lambda x: x.company_id and not x.use_payment_pro):
            bundle_journal_id = rec.company_id._get_bundle_journal(rec.payment_type)
            rec.available_journal_ids = rec.available_journal_ids.filtered(lambda x: x._origin.id != bundle_journal_id)
