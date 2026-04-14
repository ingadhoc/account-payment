from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    payment_matched_currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_payment_matched_values",
    )
    payment_matched_amount = fields.Monetary(
        compute="_compute_payment_matched_values",
        currency_field="payment_matched_currency_id",
    )

    @api.depends_context("matched_payment_ids")
    def _compute_payment_matched_values(self):
        """
        Recibiendo matched_payment_ids por contexto, devuelve el importe cancelado
        para cada línea expresado en moneda B (destination_currency_id del pago).
        """
        matched_payment_ids = self.env.context.get("matched_payment_ids")

        if not matched_payment_ids:
            self.payment_matched_currency_id = False
            self.payment_matched_amount = 0.0
            return

        payments = self.env["account.payment"].browse(matched_payment_ids).exists()

        # Moneda destino: usamos el primer pago como referencia (normalmente hay uno)
        main_payment = payments[:1]
        target_currency = main_payment.destination_currency_id or main_payment.company_currency_id
        company_currency = main_payment.company_currency_id
        accounting_rate = main_payment.accounting_rate or 1.0
        counterpart_rate = main_payment.counterpart_rate or 1.0

        # Líneas del pago que tocan cuentas AR/AP
        payment_lines = payments.move_id.line_ids.filtered(
            lambda x: x.account_type in ["asset_receivable", "liability_payable"]
        )

        for rec in self:
            debit_partials = payment_lines.mapped("matched_debit_ids").filtered(lambda x: x.debit_move_id == rec)
            credit_partials = payment_lines.mapped("matched_credit_ids").filtered(lambda x: x.credit_move_id == rec)

            if target_currency == company_currency:
                # Target es C (moneda de la compañía): usamos partial.amount que siempre está en C.
                # Esto cubre correctamente los casos reconcile_on_company_currency donde
                # rec.currency_id puede ser B1 ≠ A (ej. caso 10: factura USD, journal EUR,
                # target ARS). Usar debit/credit_amount_currency en ese escenario trataría
                # el importe en B1 como si ya estuviera en C.
                # Para casos sin reconcile donde target=C (ej. caso 1 todo ARS, caso 4
                # USD→ARS), partial.amount también da el resultado correcto.
                amount_in_b = sum(debit_partials.mapped("amount")) - sum(credit_partials.mapped("amount"))
            else:
                # Usamos debit_amount_currency / credit_amount_currency del partial, que expresan
                # el importe en la moneda propia de la línea (rec.currency_id).
                # Esto es correcto porque:
                #   - La línea AP de una factura USD tiene credit_amount_currency = monto_USD real
                #   - La línea AP de una entrada EXCH (sólo ARS) tiene amount_currency=0,
                #     por tanto credit_amount_currency=0 → no infla el importe de la factura
                # Usar partial.amount (siempre en ARS) y convertir con la tasa del pago daba
                # resultados incorrectos: e.g. 640,39 USD para la factura y 213,46 para el EXCH
                # en lugar de 853,85 USD y 0 respectivamente.
                debit_amount_rec = sum(debit_partials.mapped("debit_amount_currency"))
                credit_amount_rec = sum(credit_partials.mapped("credit_amount_currency"))
                amount_in_rec_currency = debit_amount_rec - credit_amount_rec

                # Convertir desde la moneda de rec hasta B, si difieren
                rec_currency = rec.currency_id or company_currency
                if rec_currency == target_currency:
                    amount_in_b = amount_in_rec_currency
                elif rec_currency == company_currency:
                    # rec está en C, target es B != C → C → A → B
                    amount_in_a = amount_in_rec_currency * accounting_rate
                    if target_currency == main_payment.currency_id:
                        amount_in_b = amount_in_a
                    else:
                        amount_in_b = amount_in_a * counterpart_rate
                else:
                    # rec está en A (misma que pago), target es B
                    if target_currency == main_payment.currency_id:
                        amount_in_b = amount_in_rec_currency
                    else:
                        amount_in_b = amount_in_rec_currency * counterpart_rate

            rec.payment_matched_currency_id = target_currency
            rec.payment_matched_amount = amount_in_b

    def action_register_payment(self, ctx=None):
        to_pay_partners = self.mapped("move_id.commercial_partner_id") or self.mapped("partner_id")
        company_pay_pro = len(self.mapped("company_id").ids) == 1 and self.mapped("company_id").use_payment_pro
        payment_pro = self.env.context.get("force_payment_pro")
        # si force_payment_pro se pasa como False estamos forzando no usar payment pro, vamos a metodo original
        # usamos payment pro si lo pasamos forzado (Caso pay and new donde todavia no tenemos company) o si estoy
        # pagando deuda de una sola cia y tiene payment pro
        # y si ademas estoy pagando solo deuda de un partner
        if payment_pro is not False and ((payment_pro or company_pay_pro) and len(to_pay_partners) <= 1):
            to_pay_move_lines = self.filtered(
                lambda r: not r.reconciled and r.account_id.account_type in ["asset_receivable", "liability_payable"]
            )
            if not to_pay_move_lines:
                partner_type = self.env.context.get("default_partner_type")
                to_pay_partner_id = self.env.context.get("default_partner_id")
                company_id = self.env.context.get("default_company_id")
                if not partner_type or not to_pay_partner_id:
                    raise UserError(_("Nothing to be paid on selected entries"))
            else:
                to_pay_partner_id = to_pay_partners.id
                partner_type = (
                    "customer" if to_pay_move_lines[0].account_id.account_type == "asset_receivable" else "supplier"
                )
                company_id = self.company_id.id
            to_pay_amount = sum(line.amount_residual for line in to_pay_move_lines)
            if to_pay_amount > 0:
                payment_type = "inbound"
            elif to_pay_amount < 0:
                payment_type = "outbound"
            else:
                payment_type = "inbound" if partner_type == "customer" else "outbound"
            create_and_new = True if self.env.context.get("create_and_new") else False
            context = {
                "active_model": "account.move.line",
                "active_ids": self.ids,
                "default_payment_type": payment_type,
                "default_partner_type": partner_type,
                "default_partner_id": to_pay_partner_id,
                "default_amount": abs(to_pay_amount),
                "default_amount_exact": abs(to_pay_amount),
                "default_to_pay_move_line_ids": to_pay_move_lines.ids,
                # We set this because if became from other view and in the context has 'create=False'
                # you can't crate payment lines (for ej: subscription)
                "create": True,
                "create_and_new": create_and_new,
                "default_company_id": company_id,
            }
            if self.env.context.get("default_l10n_ar_fiscal_position_id") is not None:
                context["default_l10n_ar_fiscal_position_id"] = self.env.context.get(
                    "default_l10n_ar_fiscal_position_id"
                )
            return {
                "name": _("Register Payment"),
                "res_model": "account.payment",
                "view_mode": "form",
                "views": [[False, "form"]],
                "context": context,
                "target": "current",
                "type": "ir.actions.act_window",
            }
        else:
            return super().action_register_payment(ctx=ctx)
