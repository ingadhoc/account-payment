from odoo import models


class AccountPaymentWithholdingLine(models.Model):
    _inherit = "account.payment.withholding.line"

    def _prepare_base_line_for_taxes_computation(self):
        """Value the withholding at the rate of the payment, the one its liquidity line uses, not the one of the day."""
        base_line = super()._prepare_base_line_for_taxes_computation()
        payment = self.payment_id
        company_currency = self.company_id.currency_id
        rate = payment.accounting_rate
        if not payment.use_payment_pro or not rate or payment.currency_id == company_currency:
            return base_line
        base_line["rate"] = rate
        base_line["manual_total_excluded"] = company_currency.round(self.base_amount / rate)
        for tax_amounts in (base_line.get("manual_tax_amounts") or {}).values():
            tax_amounts["base_amount"] = company_currency.round(tax_amounts["base_amount_currency"] / rate)
            tax_amounts["tax_amount"] = company_currency.round(tax_amounts["tax_amount_currency"] / rate)
        return base_line
