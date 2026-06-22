from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    other_currency = fields.Boolean(compute="_compute_other_currency")
    force_amount_company_currency = fields.Monetary(
        string="Forced Amount on Company Currency",
        currency_field="company_currency_id",
    )
    amount_company_currency = fields.Monetary(
        string="Amount on Company Currency",
        compute="_compute_amount_company_currency",
        inverse="_inverse_amount_company_currency",
        currency_field="company_currency_id",
    )
    exchange_rate = fields.Float(
        string="Exchange Rate",
        compute="_compute_exchange_rate",
        digits=(16, 6),
    )

    @api.depends("currency_id", "company_currency_id")
    def _compute_other_currency(self):
        for wizard in self:
            wizard.other_currency = bool(
                wizard.currency_id
                and wizard.company_currency_id
                and wizard.currency_id != wizard.company_currency_id
            )

    @api.depends("amount", "currency_id", "company_id", "payment_date", "other_currency", "force_amount_company_currency")
    def _compute_amount_company_currency(self):
        for wizard in self:
            if not wizard.other_currency:
                wizard.amount_company_currency = wizard.amount
            elif wizard.force_amount_company_currency:
                wizard.amount_company_currency = wizard.force_amount_company_currency
            else:
                wizard.amount_company_currency = wizard.currency_id._convert(
                    wizard.amount,
                    wizard.company_currency_id,
                    wizard.company_id,
                    wizard.payment_date or fields.Date.context_today(wizard),
                )

    def _inverse_amount_company_currency(self):
        for wizard in self:
            if wizard.other_currency:
                auto_amount = wizard.currency_id._convert(
                    wizard.amount,
                    wizard.company_currency_id,
                    wizard.company_id,
                    wizard.payment_date or fields.Date.context_today(wizard),
                )
                if wizard.company_currency_id.compare_amounts(
                    wizard.amount_company_currency, auto_amount
                ) != 0:
                    wizard.force_amount_company_currency = wizard.amount_company_currency
                else:
                    wizard.force_amount_company_currency = False
            else:
                wizard.force_amount_company_currency = False

    @api.depends("amount", "amount_company_currency", "other_currency")
    def _compute_exchange_rate(self):
        for wizard in self:
            if wizard.other_currency and wizard.amount:
                wizard.exchange_rate = wizard.amount_company_currency / wizard.amount
            else:
                wizard.exchange_rate = False

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.other_currency and self.force_amount_company_currency:
            payment_vals["force_balance"] = self.force_amount_company_currency
        return payment_vals

    def _create_payment_vals_from_batch(self, batch_result):
        payment_vals = super()._create_payment_vals_from_batch(batch_result)
        if self.other_currency and self.force_amount_company_currency:
            payment_vals["force_balance"] = self.force_amount_company_currency
        return payment_vals
