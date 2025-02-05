from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    check_add_debit_button = fields.Boolean(
        string="Agregar botón de débito",
        store=True,
        readonly=False,
        help="Si marca esta opción podrá debitar los cheques con un botón desde los mismos. Para realizar el asiento de débito se buscará un método de pago saliente del tipo Manual con nombre Manual, si no se encuentra uno se utilizará el primero que sea del tipo Manual (sin importar el nombre). Se utilizará luego la cuenta configurada en dicho método de ese método de pago.",
    )
