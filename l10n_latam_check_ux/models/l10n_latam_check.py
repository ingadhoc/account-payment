from odoo import api, fields, models


class l10nLatamAccountPaymentCheck(models.Model):
    _inherit = "l10n_latam.check"

    check_add_debit_button = fields.Boolean(related="original_journal_id.check_add_debit_button", readonly=True)
    first_operation = fields.Many2one(
        "account.payment",
        compute="_compute_first_operation",
        store=True,
        readonly=True,
    )
    date = fields.Date(related="first_operation.date")

    @api.depends("operation_ids.state")
    def _compute_first_operation(self):
        for rec in self:
            all_operations = rec.payment_id + rec.operation_ids
            valid_ops = all_operations.filtered(lambda x: x.state in ["in_process", "paid"])
            sorted_ops = valid_ops.sorted(key=lambda payment: (payment.date, payment._origin.id))
            rec.first_operation = sorted_ops[:1].id or False
