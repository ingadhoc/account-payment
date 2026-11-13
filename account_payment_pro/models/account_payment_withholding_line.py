from odoo import models


class AccountPaymentWithholdingLine(models.Model):
    _inherit = "account.payment.withholding.line"

    def _get_company_currency_amounts(self):
        """Base and amount of the line in company currency, the ones its journal item gets.

        By default, the line converted at the rate of the payment. A localization that computes the withholding in
        company currency returns its own values, so they are not rounded back from the payment currency.
        """
        self.ensure_one()
        company_currency = self.company_id.currency_id
        rate = self.payment_id.accounting_rate
        return {
            "base_amount": company_currency.round(self.base_amount / rate),
            "amount": company_currency.round(self.amount / rate),
        }

    def _prepare_base_line_for_taxes_computation(self):
        """Value the withholding at the rate of the payment, the one its liquidity line uses, not the one of the day."""
        base_line = super()._prepare_base_line_for_taxes_computation()
        payment = self.payment_id
        rate = payment.accounting_rate
        if not payment.use_payment_pro or not rate or payment.currency_id == self.company_id.currency_id:
            return base_line
        amounts = self._get_company_currency_amounts()
        base_line["rate"] = rate
        base_line["manual_total_excluded"] = amounts["base_amount"]
        for tax_amounts in (base_line.get("manual_tax_amounts") or {}).values():
            tax_amounts["base_amount"] = amounts["base_amount"]
            tax_amounts["tax_amount"] = -amounts["amount"]
        return base_line
