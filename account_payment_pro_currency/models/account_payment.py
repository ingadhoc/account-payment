from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    counterpart_currency_amount = fields.Monetary(
        currency_field="counterpart_currency_id",
        compute="_compute_counterpart_currency_amount",
    )
    counterpart_currency_id = fields.Many2one("res.currency")
    counterpart_exchange_rate = fields.Float(
        readonly=False,
        compute="_compute_counterpart_exchange_rate",
        store=True,
        precompute=True,
        copy=False,
        digits=0,
    )
    journal_currency_id = fields.Many2one(related="journal_id.currency_id", string="Journal Currency")

    @api.depends("payment_total", "counterpart_exchange_rate")
    def _compute_counterpart_currency_amount(self):
        for rec in self:
            if rec.counterpart_currency_id and rec.counterpart_exchange_rate:
                rec.counterpart_currency_amount = rec.payment_total / rec.counterpart_exchange_rate
            else:
                rec.counterpart_currency_amount = False

    @api.depends("counterpart_currency_id", "company_id", "date")
    def _compute_counterpart_exchange_rate(self):
        for rec in self:
            if rec.counterpart_currency_id:
                rate = self.env["res.currency"]._get_conversion_rate(
                    from_currency=rec.company_currency_id,
                    to_currency=rec.counterpart_currency_id,
                    company=rec.company_id,
                    date=rec.date,
                )
                rec.counterpart_exchange_rate = 1 / rate if rate else False
            else:
                rec.counterpart_exchange_rate = False

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        if not self.company_id.use_payment_pro:
            return super()._prepare_move_line_default_vals(
                write_off_line_vals=write_off_line_vals, force_balance=force_balance
            )
        write_off_line_vals = []
        if self.write_off_amount:
            if self.payment_type == "inbound":
                # Receive money.
                write_off_amount_currency = self.write_off_amount
            else:
                # Send money.
                write_off_amount_currency = -self.write_off_amount

            write_off_line_vals.append(
                {
                    "name": self.write_off_type_id.label or self.write_off_type_id.name,
                    "account_id": self.write_off_type_id.account_id.id,
                    "partner_id": self.partner_id.id,
                    "currency_id": self.currency_id.id,
                    "amount_currency": write_off_amount_currency,
                    "balance": self.currency_id._convert(
                        write_off_amount_currency, self.company_id.currency_id, self.company_id, self.date
                    ),
                }
            )
        res = super()._prepare_move_line_default_vals(
            write_off_line_vals=write_off_line_vals, force_balance=force_balance
        )
        if self.force_amount_company_currency:
            difference = self.force_amount_company_currency - res[0]["credit"] - res[0]["debit"]
            if res[0]["credit"]:
                liquidity_field = "credit"
                counterpart_field = "debit"
            else:
                liquidity_field = "debit"
                counterpart_field = "credit"
            res[0].update(
                {
                    liquidity_field: self.force_amount_company_currency,
                }
            )
            res[1].update(
                {
                    counterpart_field: res[1][counterpart_field] + difference,
                }
            )

        if self._use_counterpart_currency():
            if self.payment_type == "inbound":
                # Receive money.
                liquidity_amount_currency = self.counterpart_currency_amount
            elif self.payment_type == "outbound":
                # Send money.
                liquidity_amount_currency = -self.counterpart_currency_amount
            res[1].update(
                {
                    "currency_id": self.counterpart_currency_id.id,
                    "amount_currency": -liquidity_amount_currency,
                }
            )
        return res

    def _use_counterpart_currency(self):
        self.ensure_one()
        return (
            self.counterpart_currency_id
            and self.currency_id == self.company_id.currency_id
            and self.counterpart_currency_id != self.currency_id
        )

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        res = super()._get_trigger_fields_to_synchronize()
        return res + ('counterpart_currency_id', 'counterpart_exchange_rate')

    def _synchronize_from_moves(self, changed_fields):
        # Pisamos este método para eliminar la validación de la moneda (FW de 16, en 18 no existe más la restricción)

        if self._context.get('skip_account_move_synchronization'):
            return

        for pay in self.with_context(skip_account_move_synchronization=True):

            # After the migration to 14.0, the journal entry could be shared between the account.payment and the
            # account.bank.statement.line. In that case, the synchronization will only be made with the statement line.
            if pay.move_id.statement_line_id:
                continue

            move = pay.move_id
            move_vals_to_write = {}
            payment_vals_to_write = {}

            if 'journal_id' in changed_fields:
                if pay.journal_id.type not in ('bank', 'cash'):
                    raise UserError(_("A payment must always belongs to a bank or cash journal."))

            if 'line_ids' in changed_fields:
                all_lines = move.line_ids
                liquidity_lines, counterpart_lines, writeoff_lines = pay._seek_for_lines()

                if len(liquidity_lines) != 1:
                    raise UserError(_(
                        "Journal Entry %s is not valid. In order to proceed, the journal items must "
                        "include one and only one outstanding payments/receipts account.",
                        move.display_name,
                    ))

                if len(counterpart_lines) != 1:
                    raise UserError(_(
                        "Journal Entry %s is not valid. In order to proceed, the journal items must "
                        "include one and only one receivable/payable account (with an exception of "
                        "internal transfers).",
                        move.display_name,
                    ))

                # if any(line.currency_id != all_lines[0].currency_id for line in all_lines):
                #     raise UserError(_(
                #         "Journal Entry %s is not valid. In order to proceed, the journal items must "
                #         "share the same currency.",
                #         move.display_name,
                #     ))

                if any(line.partner_id != all_lines[0].partner_id for line in all_lines):
                    raise UserError(_(
                        "Journal Entry %s is not valid. In order to proceed, the journal items must "
                        "share the same partner.",
                        move.display_name,
                    ))

                if counterpart_lines.account_id.account_type == 'asset_receivable':
                    partner_type = 'customer'
                else:
                    partner_type = 'supplier'

                liquidity_amount = liquidity_lines.amount_currency

                move_vals_to_write.update({
                    'currency_id': liquidity_lines.currency_id.id,
                    'partner_id': liquidity_lines.partner_id.id,
                })
                payment_vals_to_write.update({
                    'amount': abs(liquidity_amount),
                    'partner_type': partner_type,
                    'currency_id': liquidity_lines.currency_id.id,
                    'destination_account_id': counterpart_lines.account_id.id,
                    'partner_id': liquidity_lines.partner_id.id,
                })
                if liquidity_amount > 0.0:
                    payment_vals_to_write.update({'payment_type': 'inbound'})
                elif liquidity_amount < 0.0:
                    payment_vals_to_write.update({'payment_type': 'outbound'})

            move.write(move._cleanup_write_orm_values(move, move_vals_to_write))
            pay.write(move._cleanup_write_orm_values(pay, payment_vals_to_write))
