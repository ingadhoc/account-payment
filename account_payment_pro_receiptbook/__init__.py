from . import models
from . import wizard
from odoo import api, _
from odoo.exceptions import UserError
from .hooks import uninstall_hook
from odoo.addons.account.wizard.account_resequence import AccountResequenceWizard


def _generate_receiptbooks(env):
    """Create receiptbooks on existing companies with chart installed"""
    with_chart_companies = env["res.company"].search([("chart_template", "!=", False)])
    for company in with_chart_companies:
        env["account.chart.template"]._create_receiptbooks(company)


def monkey_patches():
    def default_get_patch(self, fields_list):
        values = super(AccountResequenceWizard, self).default_get(fields_list)
        if "move_ids" not in fields_list:
            return values
        active_move_ids = self.env["account.move"]
        if self.env.context["active_model"] == "account.move" and "active_ids" in self.env.context:
            active_move_ids = self.env["account.move"].browse(self.env.context["active_ids"])

        # Comprobamos si todos los diarios tienen el mismo receiptbook
        if all(move.receiptbook_id for move in active_move_ids):
            if len(active_move_ids.receiptbook_id) > 1:
                raise UserError(_("You can only resequence items from the same receiptbook"))
        elif any(move.receiptbook_id for move in active_move_ids):
            raise UserError(
                _(
                    "You can only resequence items if all selected moves belong to the same receiptbook, or if none have a receiptbook assigned."
                )
            )
        else:
            # Método original de odoo
            if len(active_move_ids.journal_id) > 1:
                raise UserError(_("You can only resequence items from the same journal"))
            move_types = set(active_move_ids.mapped("move_type"))
            if (
                active_move_ids.journal_id.refund_sequence
                and ("in_refund" in move_types or "out_refund" in move_types)
                and len(move_types) > 1
            ):
                raise UserError(
                    _(
                        "The sequences of this journal are different for Invoices and Refunds but you selected some of both types."
                    )
                )
            is_payment = set(active_move_ids.mapped(lambda x: bool(x.origin_payment_id)))
            if active_move_ids.journal_id.payment_sequence and len(is_payment) > 1:
                raise UserError(
                    _(
                        "The sequences of this journal are different for Payments and non-Payments but you selected some of both types."
                    )
                )

        values["move_ids"] = [(6, 0, active_move_ids.ids)]
        return values

    def propagate(method1, method2):
        """Propagate decorators from ``method1`` to ``method2``, and return the
        resulting method.
        """
        if method1:
            for attr in ("_returns",):
                if hasattr(method1, attr) and not hasattr(method2, attr):
                    setattr(method2, attr, getattr(method1, attr))
        return method2

    def _patch_method(cls, name, method):
        """Método para aplicar monkey patches.
        cls --> clase
        name --> nombre del método original
        method --> nombre del método que tiene el parche"""

        origin = getattr(cls, name)
        method.origin = origin
        wrapped = propagate(origin, method)
        wrapped.origin = origin
        setattr(cls, name, wrapped)

    _patch_method(AccountResequenceWizard, "default_get", default_get_patch)
