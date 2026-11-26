##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import (
    Command,
    fields as ofields,
)
from odoo.exceptions import ValidationError
from odoo.tests.common import tagged

from .common import LatamCheckCommon


@tagged("post_install", "-at_install")
class TestThirdPartyCheckLifecycle(LatamCheckCommon):
    """Third party check lifecycle, walked as a chain: a check breaks when
    one operation leaves state the next misreads, so each ``subTest`` checks
    after a step, not just at the end.

    Invariants (balanced entry, no filler line, ...) come from account_ux's
    battery, called after each operation — not repeated here.

    "State" isn't a stored field: it's ``current_journal_id``, recomputed
    from the last non-draft/non-canceled operation. ``inbound`` leaves it
    set to that journal; ``outbound`` leaves it empty (out of the wallet).
    """

    def setUp(self):
        super().setUp()
        self.operation_base = ofields.Datetime.to_datetime("2026-01-01 08:00:00")

    # ------------------------------------------------------------------
    # helpers del ciclo
    # ------------------------------------------------------------------
    def _transfer(self, checks, destination, step=1):
        """Wallet transfer via the mass-transfer wizard, like the UI does.
        Building the payments by hand takes the journal's currency instead
        of the check's and gets blocked for a different reason.

        ``step`` orders transfers between them: ``operation_date`` copies
        from ``create_date``, which freezes within one DB transaction, so
        every operation in the test would tie without an explicit offset.
        """
        outbound = (
            self.env["l10n_latam.payment.mass.transfer"]
            .with_context(active_model="l10n_latam.check", active_ids=checks.ids)
            .create({"destination_journal_id": destination.id})
            ._create_payments()
        )
        inbound = self._last_operation_of(checks[0], "inbound")
        self._stamp_operation(outbound, step * 10)
        self._stamp_operation(inbound, step * 10 + 1)
        checks.invalidate_recordset()
        # the wizard runs with check_deposit_transfer=True, which skips the hook
        # that on a manual internal transfer forces this recompute (account_payment.py,
        # _create_paired_internal_transfer_payment) - without it, current_journal_id
        # stays frozen at whatever it was when the last payment posted, before the
        # stamps above changed the ordering
        checks._compute_current_journal()
        # a transfer is two entries; both must be sound
        for payment in outbound + inbound:
            self.assert_payment_invariants(payment, "pase de cartera")
        return outbound

    def _receive(self, amounts, numbers):
        """Third party check receipt, posted and anchored at step 0 so it
        sorts before any transfer the test declares."""
        receipt = self._receive_third_party_checks(amounts, numbers=numbers)
        receipt.action_post()
        self._stamp_operation(receipt, 0)
        receipt.l10n_latam_new_check_ids.invalidate_recordset()
        return receipt

    def _stamp_operation(self, payments, minutes):
        """Sets the timestamp the check uses to order its operations."""
        payments.write(
            {"l10n_latam_move_check_ids_operation_date": ofields.Datetime.add(self.operation_base, minutes=minutes)}
        )

    def _last_operation_of(self, check, payment_type):
        return check.operation_ids.filtered(
            lambda pay: pay.payment_type == payment_type and pay.state not in ("draft", "canceled")
        ).sorted("id")[-1:]

    def _revert_last_transfer(self, check):
        """Undo the last transfer. A transfer is two linked payments (out +
        in); resetting the inbound one drags the outbound along, so it's one
        operation, not two — reverting them separately fails because the
        second is no longer the check's last operation.
        """
        inbound = self._last_operation_of(check, "inbound")
        outbound = inbound.paired_internal_transfer_payment_id
        inbound.action_draft()
        check.invalidate_recordset()
        for payment in (inbound + outbound).filtered(lambda pay: pay.move_id):
            self.assert_payment_invariants(payment, "pase de cartera revertido")
        return inbound

    def _on_hand_in(self, journal):
        """Checks currently in that journal's wallet."""
        return self.env["l10n_latam.check"].search(
            [("company_id", "=", self.company.id), ("current_journal_id", "=", journal.id)]
        )

    # ------------------------------------------------------------------
    # T17
    # ------------------------------------------------------------------
    def test_third_party_check_travels_and_comes_back(self):
        """Check travels: wallet → transfer → revert → endorsement → draft.

        Covers FCP-R11-E1/E2/E3 and FCP-R12-E1/E4/E5/E6. Integration test:
        no way to verify this without orchestrating payment, entry and check.

        Not implemented, declared:
        - FCP-R11-E4 (A→B→C chain reverting only the second transfer):
          ``operation_date`` ties within one transaction, so ordering a
          three-transfer chain needs that resolved first.
        - FCP-R12-E8 (checks across two companies): a second Argentine
          company is rejected by ``saas_client_account`` on OBA databases.
        """
        cartera_b = self._create_third_party_journal("Test Third Party Checks B", "TTPCB")

        receipt = self._receive([20000.0], ["00000001"])
        check = receipt.l10n_latam_new_check_ids

        with self.subTest("el cheque recién cobrado queda en su cartera y es elegible"):
            self.assertEqual(check.current_journal_id, self.third_party_journal)
            self.assertIn(check, self._on_hand_in(self.third_party_journal))
            self.assert_check_lines_match(receipt, "cobro del cheque")
            self.assert_payment_invariants(receipt, "cobro del cheque")

        with self.subTest("pasado a otra cartera sigue en cartera y no cambia de importe"):
            self._transfer(check, cartera_b, step=1)
            self.assertEqual(check.current_journal_id, cartera_b)
            self.assertEqual(check.amount, 20000.0)
            self.assertNotIn(check, self._on_hand_in(self.third_party_journal))
            self.assertIn(check, self._on_hand_in(cartera_b))

        with self.subTest("revertir el pase lo devuelve a la cartera de origen"):
            self._revert_last_transfer(check)
            self.assertEqual(check.current_journal_id, self.third_party_journal)
            self.assertIn(check, self._on_hand_in(self.third_party_journal))
            self.assertNotIn(check, self._on_hand_in(cartera_b))
            self.assertEqual(check.payment_id, receipt, "el cheque sigue colgado de su cobro")

        with self.subTest("endosado a un proveedor deja de estar disponible"):
            # bug histórico: un cheque endosado se podía volver a aplicar a otra deuda
            endorsement = self._deliver_third_party_checks(check)
            endorsement.action_post()
            self._stamp_operation(endorsement, 30)
            check.invalidate_recordset()
            self.assertFalse(check.current_journal_id, "un cheque entregado ya no está en ninguna cartera")
            self.assertNotIn(check, self._on_hand_in(self.third_party_journal))
            self.assert_payment_invariants(endorsement, "endoso del cheque")

        with self.subTest("volver el endoso a borrador lo devuelve a la cartera donde estaba"):
            endorsement.action_draft()
            check.invalidate_recordset()
            self.assertEqual(check.current_journal_id, self.third_party_journal)
            self.assertEqual(
                self.env["l10n_latam.check"].search_count([("id", "=", check.id), ("current_journal_id", "!=", False)]),
                1,
                "el cheque tiene que estar en una sola cartera",
            )

    def test_third_party_checks_of_equal_amount_do_not_cross(self):
        """Three checks of the same amount don't cross lines when
        transferred together. Covers FCP-R11-E6."""
        cartera_b = self._create_third_party_journal("Test Third Party Checks B", "TTPCB")

        receipt = self._receive([20000.0, 20000.0, 20000.0], ["00000011", "00000012", "00000013"])
        checks = receipt.l10n_latam_new_check_ids

        with self.subTest("cada cheque cobrado tiene su propio apunte"):
            self.assert_check_lines_match(receipt, "cobro de tres cheques iguales")
            self.assert_payment_invariants(receipt, "cobro de tres cheques iguales")

        with self.subTest("los tres se pasan de cartera y ninguno queda atrás"):
            self._transfer(checks, cartera_b, step=1)
            self.assertEqual(
                checks.mapped("current_journal_id"),
                cartera_b,
                "los tres cheques tienen que quedar en la cartera destino",
            )
            self.assertEqual(set(checks.mapped("amount")), {20000.0})

        with self.subTest("cada cheque conserva su número y su apunte pendiente"):
            self.assertEqual(len(checks.mapped("outstanding_line_id")), 3)
            self.assertEqual(
                sorted(checks.mapped("name")),
                ["00000011", "00000012", "00000013"],
            )

    def test_editing_the_original_receipt_afterwards_does_not_relocate_the_check(self):
        """Editar el recibo original (asignarle otro cliente) después de
        transferir el cheque no lo reubica: el efecto de la edición queda
        en el recibo, no en el cheque, que ya viajó a otra cartera.

        Cubre FCP-R11-E5 (``CHK-029``): el bug reportado es justo que el
        efecto de editar un objeto aparecía en otro distinto.
        """
        cartera_b = self._create_third_party_journal("Test Third Party Checks B", "TTPCB")
        other_customer = self.env["res.partner"].create({"name": "Test R11-E5 Other Customer", "vat": "30710158264"})

        receipt = self._receive([20000.0], ["00000041"])
        check = receipt.l10n_latam_new_check_ids
        self._transfer(check, cartera_b, step=1)
        self.assertEqual(check.current_journal_id, cartera_b, "pasado a la cartera B antes de editar el recibo")

        receipt.partner_id = other_customer.id
        check.invalidate_recordset()

        with self.subTest("el cheque sigue en la cartera destino, sin reubicarse"):
            self.assertEqual(check.current_journal_id, cartera_b)
            self.assertIn(check, self._on_hand_in(cartera_b))

        with self.subTest("el cambio quedó en el recibo, no se propagó al cheque"):
            self.assertEqual(check.payment_id, receipt)
            self.assertEqual(receipt.partner_id, other_customer)

    # ------------------------------------------------------------------
    # T18
    # ------------------------------------------------------------------
    def test_transfer_currency_comes_from_the_check_not_the_payment(self):
        """La moneda del pase la fija el cheque, no el pago armado a mano.

        Dado un cheque de terceros en USD, cuando se pasa de cartera por el
        wizard, entonces el pase se permite y el cheque llega intacto en USD
        (D11). Cuando el mismo pase se arma a mano forzando la moneda de la
        compañía, entonces la validación lo frena.

        Cubre FCP-R11-E7/E8. Se demuestra en rojo sacando el chequeo de
        moneda de ``_get_blocking_l10n_latam_warning_msg``.
        """
        cartera_b = self._create_third_party_journal("Test Third Party Checks B", "TTPCB")
        receipt = self._receive_third_party_checks([100.0], numbers=["00000021"], currency=self.foreign_currency)
        receipt.action_post()
        self._stamp_operation(receipt, 0)
        check = receipt.l10n_latam_new_check_ids
        check.invalidate_recordset()

        with self.subTest("por el wizard, la moneda del cheque no se toca"):
            self._transfer(check, cartera_b, step=1)
            self.assertEqual(check.current_journal_id, cartera_b)
            self.assertEqual(check.currency_id, self.foreign_currency)
            self.assertEqual(check.amount, 100.0)

        with self.subTest("armado a mano con otra moneda, la validación lo frena"):
            manual = self.env["account.payment"].create(
                {
                    "payment_type": "outbound",
                    "partner_id": self.company.partner_id.id,
                    "journal_id": cartera_b.id,
                    "company_id": self.company.id,
                    "date": self.today,
                    "amount": 100.0,
                    "currency_id": self.company_currency.id,
                    "payment_method_line_id": self._get_method_line(cartera_b, "out_third_party_checks").id,
                    "l10n_latam_move_check_ids": [Command.set(check.ids)],
                }
            )
            with self.assertRaises(ValidationError):
                manual.action_post()
            self.assertEqual(check.current_journal_id, cartera_b, "el cheque no se movió con el intento fallido")
            self.assertEqual(check.currency_id, self.foreign_currency, "ni cambió de moneda")

    def test_deposited_check_rejection_reopens_the_debt_and_a_new_check_closes_it(self):
        """Cheque depositado, rechazado y repuesto por el cliente.

        Dada una factura de $20.000 cobrada con un cheque de terceros y
        depositado en el banco, cuando el banco lo rechaza, entonces el
        cheque sale de cartera y la deuda del cliente se reabre por
        $20.000; cuando el cliente la cubre con un cheque nuevo, entonces
        la deuda vuelve a cero y el cheque rechazado no vuelve a cartera.

        Cubre FCP-R12-E2/E3/E7 y FCP-R13-E5 (el rechazo de un cheque
        depositado deja un apunte conciliable contra el banco). FCP-R13-E4
        (líneas del depósito, cheques de terceros) ya está cubierto por
        ``test_deposit_to_bank`` en ``test_third_party_checks_ux.py`` — no
        se repite acá.

        Escenario declarado y NO implementado: el control positivo de que un
        cheque ya devuelto al cliente no se puede volver a rechazar
        (``can_reject`` debería quedar en ``False``). ``_compute_can_reject``
        compara ``op.state == "posted"``, pero ``account.payment.state``
        nunca vale eso (sus valores son draft/in_process/paid/canceled/
        rejected) — la guarda no dispara nunca y el cheque queda rechazable
        dos veces. Es un bug de producto, no de este test: escribir
        ``assertTrue(check.can_reject)`` acá blindaría el bug como si fuera
        el comportamiento esperado. Se retoma cuando se corrija
        ``l10n_latam_check_ux/models/l10n_latam_check.py:106-110``.
        """
        income = self._create_account("TCHKINC", "Test Check Income", "income")
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_date": self.today,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Test check rejection line",
                            "quantity": 1,
                            "price_unit": 20000.0,
                            "account_id": income.id,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        invoice.action_post()

        receipt = self._receive([20000.0], ["00000031"])
        check = receipt.l10n_latam_new_check_ids
        (invoice.line_ids + receipt.move_id.line_ids).filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        ).reconcile()

        with self.subTest("cobrada y depositada, la deuda queda saldada"):
            self.assert_partner_balance(self.partner, 0.0)
            self._transfer(check, self.bank_journal, step=1)
            self.assertEqual(check.current_journal_id, self.bank_journal)
            self.assertNotIn(check, self._on_hand_in(self.third_party_journal), "depositado, ya no está en cartera")

        with self.subTest("el banco lo rechaza: sale de circulación y la deuda se reabre"):
            wizard = (
                self.env["account.check.reject.wizard"]
                .with_context(active_model="l10n_latam.check", active_ids=check.ids)
                .create({"date": self.today, "rejected_journal_id": self.rejected_journal.id})
            )
            wizard.action_confirm()
            self.assertFalse(check.current_journal_id, "un cheque rechazado no vuelve a ninguna cartera")
            self.assert_partner_balance(self.partner, 20000.0, msg="la deuda se reabre por el importe del cheque")

        with self.subTest("el rechazo genera un apunte conciliable contra el banco"):
            # Caso B del wizard (cheque depositado): la transferencia saliente
            # desde el diario banco es la que produce el movimiento que el
            # extracto real tiene que poder calzar — el otro lado (recovery
            # hacia el cliente) es contra la cartera de rechazados, no el banco.
            # La cuenta que toca es la del cheque en el diario banco (donde vive
            # mientras está depositado, no la del efectivo/banco liso), la misma
            # que usa el resto de la suite (``third_party_account``).
            bank_transfer = check.operation_ids.filtered(
                lambda pay: pay.journal_id == self.bank_journal and pay.payment_type == "outbound"
            ).sorted("id")[-1:]
            bank_line = bank_transfer.move_id.line_ids.filtered(
                lambda line: line.account_id == self.third_party_account
            )
            self.assertTrue(bank_line, "la transferencia de rechazo toca la cuenta del cheque en el banco")
            self.assertTrue(bank_line.account_id.reconcile, "esa cuenta tiene que ser conciliable")
            self.assertFalse(bank_line.reconciled, "todavía sin calzar contra el extracto")

        with self.subTest("un cheque nuevo del cliente cancela la deuda reabierta"):
            replacement = self._receive([20000.0], ["00000032"])
            reopened = self.env["account.move.line"].search(
                [
                    ("partner_id", "=", self.partner.id),
                    ("account_id.account_type", "=", "asset_receivable"),
                    ("parent_state", "=", "posted"),
                    ("full_reconcile_id", "=", False),
                ]
            )
            (reopened + replacement.move_id.line_ids).filtered(
                lambda line: line.account_id.account_type == "asset_receivable"
            ).reconcile()
            self.assert_partner_balance(
                self.partner, 0.0, msg="sin doble crédito: la deuda cierra en cero, no en negativo"
            )
            self.assertFalse(check.current_journal_id, "el rechazado sigue fuera de cualquier cartera")
