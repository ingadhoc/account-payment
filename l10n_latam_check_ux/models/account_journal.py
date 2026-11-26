from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    check_add_debit_button = fields.Boolean(
        string="Agregar botón de débito",
        store=True,
        readonly=False,
        help=(
            "Si marca esta opción podrá debitar los cheques con un botón desde los mismos. "
            "Para realizar el asiento de débito se buscará un método de pago saliente del tipo "
            "Manual con nombre Manual, si no se encuentra uno se utilizará el primero que sea "
            "del tipo Manual (sin importar el nombre). Se utilizará luego la cuenta configurada "
            "en dicho método de ese método de pago."
        ),
    )

    def _get_check_transfer_destination_lines(self):
        """Inbound lines that can receive the checks of a transfer on this journal.

        A transfer never brings new checks, so that line is never offered. On a third party checks
        journal the checks stay in portfolio, and only the third party checks line keeps them there.
        """
        self.ensure_one()
        lines = self._get_available_payment_method_lines("inbound").filtered(
            lambda x: x.code != "new_third_party_checks"
        )
        return lines.filtered(lambda x: x.code == "in_third_party_checks") or lines
