import json

from odoo import Command, models


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
        if not rate:
            return {"base_amount": 0.0, "amount": 0.0}
        return {
            "base_amount": company_currency.round(self.base_amount / rate),
            "amount": company_currency.round(self.amount / rate),
        }

    def _prepare_withholding_amls_create_values(self):
        """One pair of base journal items per base amount, as in 19.0.

        The core books a pair per withholding, so two withholdings over the same base leave four base items
        instead of two. A base item that books the same amount on the same account as an earlier one is
        dropped, and the one that stays carries the taxes and the tax tags of both: the amounts are not added
        up, since they are the same base counted twice.
        """
        values = super()._prepare_withholding_amls_create_values()
        if not self or not self.payment_id.use_payment_pro:
            return values

        kept_by_base = {}
        merged = []
        for vals in values:
            if vals.get("tax_repartition_line_id"):
                merged.append(vals)
                continue
            base = json.dumps(
                [
                    vals.get("account_id"),
                    vals.get("currency_id"),
                    vals.get("partner_id"),
                    vals.get("analytic_distribution"),
                    vals.get("amount_currency"),
                    vals.get("balance"),
                ],
                sort_keys=True,
                default=str,
            )
            kept = kept_by_base.get(base)
            if kept is None:
                kept_by_base[base] = vals
                merged.append(vals)
                continue
            for field in ("tax_ids", "tax_tag_ids"):
                ids = set(self._get_command_set_ids(kept.get(field))) | set(self._get_command_set_ids(vals.get(field)))
                if ids:
                    kept[field] = [Command.set(sorted(ids))]
        return merged

    @staticmethod
    def _get_command_set_ids(commands):
        """IDs of a ``[Command.set([...])]`` value, empty when there is none."""
        return next((command[2] for command in commands or [] if command[0] == Command.SET), [])

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
