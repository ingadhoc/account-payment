##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountCheckActionWizard(models.TransientModel):
    _name = "account.check.action.wizard"
    _description = "Account Check Action Wizard"

    date = fields.Date(
        default=fields.Date.context_today,
        required=True,
    )

    def action_confirm(self):
        """Este método sirve para hacer el débito de cheques con cuenta outstanding desde los payments con método de pago de cheques."""
        checks = self.env["l10n_latam.check"].browse(self._context.get("active_ids", False))
        if checks.filtered(lambda x: not x.check_add_debit_button):
            raise UserError(_("At least one check is in a journal where the 'Add Debit Date' option is not enabled."))
        for check in checks:
            if self.date < check.payment_id.date:
                raise UserError(
                    _("La fecha del débito del cheque %s no puede ser inferior a la fecha de emisión del mismo %s.")
                    % (self.date, check.payment_id.date)
                )
            # Línea del cheque a conciliar.
            move_line_id = check.outstanding_line_id.ids
            # Obtenemos la cuenta outstanding del método de pago pentientes "manual" del diario del pago o bien la "Cuenta de pagos pentientes" de la compañía.
            outstanding_account = self._get_outstanding_account(check)
            # Obtenemos fecha, importe, pasamos cuenta outstanding y el diario asignado es el mismo que se está editando.
            label = f"Débito cheque nro {check.name}"
            new_mv_line_dicts = {
                "label": label,
                "amount": abs(sum(check.outstanding_line_id.mapped("balance"))),
                "account_id": outstanding_account.id,
                "journal_id": check.original_journal_id.id,
                "move_line_ids": move_line_id,
                "date": self.date,
            }
            # Aquí hacemos el asiento del débito.
            wizard = (
                self.env["account.reconcile.wizard"]
                .with_context(active_model="account.move.line", active_ids=move_line_id)
                .create(new_mv_line_dicts)
            )
            wizard.reconcile()
            debit_move = self.env["account.move"].search(
                [("line_ids.name", "=", label), ("date", "=", self.date)], limit=1
            )
            if debit_move:
                check.message_post(
                    body=f'El cheque nro "{check.name}" ha sido debitado. ' + debit_move._get_html_link()
                )
            else:
                check.message_post(
                    body=f'El cheque nro "{check.name}" ha sido debitado, pero no se encontró el asiento asociado.'
                )

    def _get_outstanding_account(self, check):
        """Obtenemos la cuenta para hacer el débito de cheques y hacemos las validaciones correspondientes. Siempre necesitamos que se encuentre establecido un método de pago manual en el diario para poder hacer el débito, no vamos a buscar la cuenta outstanding en configuración en caso de que no esté establecido el método de pago manual. Primero buscamos método de pago con code manual y nombre 'Manual' y si no lo encuentra buscamos el primer método de pago manual que se creó."""
        journal = check.original_journal_id
        journal_manual_payment_method = journal.outbound_payment_method_line_ids.filtered(lambda x: x.code == "manual")
        if not journal_manual_payment_method:
            raise UserError(
                _("No es posible crear un nuevo débito de cheque sin un método de pagos 'manual' en el diario %s.")
                % (journal.display_name)
            )
        # si hay mas de un método de pago con code code manual tratamos de buscar uno con name Manual, si no lo hay usamos el primero
        if len(journal_manual_payment_method) > 1:
            if journal_manual_payment_method.filtered(lambda x: x.name == "Manual"):
                journal_manual_payment_method = journal_manual_payment_method.filtered(lambda x: x.name == "Manual")
            journal_manual_payment_method = journal_manual_payment_method.sorted()[0]
        return journal_manual_payment_method.payment_account_id
