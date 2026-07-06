from odoo import Command
from odoo.tests import Form, tagged

from .test_payment_multimoneda import TestPaymentMultimoneda


@tagged("post_install", "-at_install")
class TestManualAmountOnDebtChange(TestPaymentMultimoneda):
    """Al quitar líneas de deuda de un pago ya guardado, no debe recalcularse el
    importe que el usuario fijó a mano.

    Con un importe fijado manualmente, al eliminar la primera línea de deuda el
    sistema pisaba ese importe llevándolo al nuevo total de la deuda, pero solo
    cuando la deuda restante superaba el importe fijado.
    """

    def test_remove_debt_line_keeps_fixed_amount(self):
        """Pago guardado, importe fijado a mano (50.000) y deuda restante mayor
        (70.000) tras quitar una línea → el importe NO debe cambiar."""
        inv1 = self._create_invoice(40000, self.ars)
        inv2 = self._create_invoice(70000, self.ars)
        line1 = self._get_debt_lines(inv1)
        debt_lines = line1 | self._get_debt_lines(inv2)

        # Pago guardado pagando ambas facturas, con importe fijado a mano por el usuario.
        payment = self._create_payment(
            self.bank_ars,
            amount=50000,
            to_pay_move_line_ids=[Command.set(debt_lines.ids)],
        )
        self.assertTrue(payment.id, "El pago debe estar guardado (origin.id seteado)")
        self.assertAlmostEqual(payment.amount, 50000, places=2)

        # El usuario quita la primera línea de deuda desde la UI. La deuda restante
        # (70.000) es mayor al importe fijado (50.000): es el caso que pisaba el monto.
        with Form(payment) as form:
            form.to_pay_move_line_ids.remove(id=line1.id)

        self.assertAlmostEqual(
            payment.amount,
            50000,
            places=2,
            msg="Quitar una línea de deuda no debe pisar el importe fijado a mano",
        )

    def test_initial_load_still_adjusts_amount(self):
        """Control: en la carga inicial (registro nuevo, líneas por default de
        action_register_payment) la corrección de tasa debe seguir aplicando.
        Garantiza que el guard no desactiva la corrección de tasa inicial."""
        invoice = self._create_invoice(110000, self.ars)
        debt_lines = self._get_debt_lines(invoice)

        with Form(
            self.env["account.payment"].with_context(
                default_partner_type="customer",
                default_payment_type="inbound",
                default_to_pay_move_line_ids=debt_lines.ids,
            )
        ) as form:
            form.journal_id = self.bank_ars
            form.partner_id = self.partner

        payment = form.record
        # Sin importe fijado a mano, el pago debe cubrir la deuda seleccionada.
        self.assertAlmostEqual(payment.to_pay_amount, payment.payment_total, places=2)
