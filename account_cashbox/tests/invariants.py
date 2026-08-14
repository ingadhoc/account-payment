##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""Batería de invariantes de las suites de caja.

Estas verificaciones no son de un caso: son las que **toda** operación de caja
tiene que cumplir siempre. La suite las llama después de cada operación, además
de los asserts puntuales que cada escenario declara.

    class TestAlgo(CashboxCommon):
        def test_algo(self):
            ...
            self.assert_cashbox_invariants(session)
            self.assert_payment_invariants(payment)

El archivo tiene dos mitades:

* **Asiento y pago** — que el asiento cierre, que no lo haya cerrado Odoo con
  una línea de relleno, que no queden líneas en cero, que en multimoneda cierre
  en las dos monedas. Estas mismas verificaciones se están escribiendo en
  ``account_ux/tests/invariants.py`` como batería compartida de cobros y pagos
  (tarea 71623, todavía sin mergear y en otro repo). **Están duplicadas acá a
  propósito**, para que esta suite no quede bloqueada por ese PR: cuando aquel
  mergee, esta mitad se borra y la clase pasa a heredar de allá. La
  deduplicación se resuelve desde ese PR.
* **Sesión de caja** — propias de este módulo y sin equivalente arriba: usan
  ``cashbox_session_id``, ``line_ids`` y los ``balance_*``.

Regla de uso, importante: **la batería no lleva flags para saltear
invariantes**. Si un escenario legítimamente viola una, la excepción se declara
en el test —a la vista y con el motivo escrito al lado— y no se esconde acá
adentro. Un helper con condicionales deja de ser una base y pasa a ser el lugar
donde se entierran los casos que nadie verifica.
"""


class CashboxInvariantsMixin:
    # ------------------------------------------------------------------
    # invariantes del asiento
    # (duplicadas de la batería de account_ux — ver docstring del módulo)
    # ------------------------------------------------------------------
    def assert_move_sums_zero(self, move, msg=""):
        """El asiento cierra en la moneda de la compañía."""
        total = move.company_currency_id.round(sum(move.line_ids.mapped("balance")))
        self.assertEqual(total, 0.0, "El asiento %s no suma cero (%s). %s" % (move.name, total, msg))

    def assert_no_automatic_balancing_line(self, move, msg=""):
        """No hay línea de balanceo automático.

        Odoo agrega una cuando el asiento no cierra por su cuenta. Que aparezca
        significa que el importe lo completó el sistema, no la operación: el
        asiento "cierra" y el error queda tapado.

        Se la identifica por **nombre**, que es como la identifica el propio
        Odoo en ``_sync_unbalanced_lines``. Buscarla por cuenta no sirve:
        ``_get_automatic_balancing_account()`` devuelve la cuenta del diario
        cuando el diario tiene una, así que en cualquier pago de banco o caja la
        línea de liquidez legítima cae en esa misma cuenta y el chequeo da
        positivo siempre.
        """
        balance_name = self.env._("Automatic Balancing Line")
        balancing = move.line_ids.filtered(lambda line: line.name == balance_name)
        self.assertFalse(
            balancing,
            "El asiento %s tiene línea de balanceo automático por %s. %s"
            % (move.name, sum(balancing.mapped("balance")), msg),
        )

    def assert_no_zero_lines(self, move, msg=""):
        """Ninguna línea en cero.

        Una línea en $0 es un mecanismo que se disparó sin tener nada que
        hacer. Ensucia el mayor y esconde el error real.
        """
        zero_lines = move.line_ids.filtered(lambda line: not line.debit and not line.credit)
        self.assertFalse(
            zero_lines,
            "El asiento %s tiene %s línea(s) en cero: %s. %s"
            % (move.name, len(zero_lines), zero_lines.mapped("name"), msg),
        )

    def assert_closes_in_both_currencies(self, move, msg=""):
        """En multimoneda el asiento cierra también en la moneda del comprobante."""
        self.assert_move_sums_zero(move, msg)
        by_currency = {}
        for line in move.line_ids.filtered(lambda line: line.currency_id != line.company_currency_id):
            by_currency.setdefault(line.currency_id, 0.0)
            by_currency[line.currency_id] += line.amount_currency
        for currency, total in by_currency.items():
            self.assertEqual(
                currency.round(total),
                0.0,
                "El asiento %s no cierra en %s (%s). %s" % (move.name, currency.name, total, msg),
            )

    def assert_payment_invariants(self, payment, msg=""):
        """Las invariantes que todo pago tiene que cumplir, en un solo lugar."""
        move = payment.move_id
        self.assert_move_sums_zero(move, msg)
        self.assert_no_automatic_balancing_line(move, msg)
        self.assert_no_zero_lines(move, msg)
        if payment.currency_id != payment.company_currency_id:
            self.assert_closes_in_both_currencies(move, msg)

    # ------------------------------------------------------------------
    # invariantes de la sesión de caja (propias de este módulo)
    # ------------------------------------------------------------------
    def assert_session_line_coverage(self, session, msg=""):
        """Las líneas de control de la sesión son una por diario, y coherentes.

        No se compara contra los diarios *actuales* de la caja a propósito: una
        sesión vieja conserva las líneas con las que nació aunque después le
        cambien los diarios a la caja, y eso es deliberado (ver el comentario en
        ``_compute_available_journal_ids``). Lo que sí tiene que valer siempre
        es que no haya diarios repetidos ni líneas sin diario.
        """
        lines = session.line_ids
        self.assertTrue(
            all(lines.mapped("journal_id")),
            "La sesión %s tiene línea(s) sin diario. %s" % (session.name, msg),
        )
        journals = lines.mapped("journal_id")
        self.assertEqual(
            len(journals),
            len(lines),
            "La sesión %s tiene diarios repetidos en sus líneas (%s líneas, %s diarios). %s"
            % (session.name, len(lines), len(journals), msg),
        )
        ajenos = journals.filtered(lambda j: j.type not in ("bank", "cash"))
        self.assertFalse(
            ajenos,
            "La sesión %s tiene líneas de diarios que no son de banco ni caja: %s. %s"
            % (session.name, ajenos.mapped("name"), msg),
        )

    def assert_session_balances_consistent(self, session, msg=""):
        """Ningún pago de la sesión queda fuera de los saldos, y los saldos cierran.

        La primera parte es la que importa: un pago cuya sesión no tiene línea
        para su diario **desaparece de todos los balances**. No falla nada, no
        hay error: la plata simplemente no se cuenta al cerrar. Es el modo de
        falla que ningún test puntual mira, porque cada test mira el saldo que
        fue a buscar.
        """
        session.line_ids.invalidate_recordset(["amount", "balance_end", "balance_difference"])
        payments = session.payment_ids.filtered(lambda p: p.state not in ("draft", "canceled"))
        con_linea = session.line_ids.mapped("journal_id")
        huerfanos = payments.filtered(lambda p: p.journal_id not in con_linea)
        self.assertFalse(
            huerfanos,
            "La sesión %s tiene %s pago(s) en diarios sin línea de control (%s): su importe no entra en ningún "
            "saldo. %s" % (session.name, len(huerfanos), huerfanos.mapped("journal_id.name"), msg),
        )
        for line in session.line_ids:
            currency = line.currency_id
            self.assertEqual(
                currency,
                line.journal_id.currency_id or line.journal_id.company_id.currency_id,
                "La línea del diario %s declara la moneda %s, que no es la del diario ni la de la compañía. %s"
                % (line.journal_id.name, currency.name, msg),
            )
            self.assertEqual(
                currency.round(line.balance_end),
                currency.round(line.balance_start + line.amount),
                "En el diario %s el saldo final (%s) no es el inicial (%s) más el movimiento (%s). %s"
                % (line.journal_id.name, line.balance_end, line.balance_start, line.amount, msg),
            )
            self.assertEqual(
                currency.round(line.balance_difference),
                currency.round(line.balance_end_real - line.balance_end),
                "En el diario %s la diferencia (%s) no es el final real (%s) menos el final (%s). %s"
                % (line.journal_id.name, line.balance_difference, line.balance_end_real, line.balance_end, msg),
            )

    def assert_cashbox_invariants(self, session, msg=""):
        """Las invariantes que toda sesión tiene que cumplir, en un solo lugar.

        No entra acá "la compañía del pago pertenece al árbol de la del diario",
        que era candidata: el ``_check_company`` del propio ORM impide construir
        el estado que detectaría, así que no se la puede probar en rojo. Una
        invariante que nadie vio fallar no demostró mirar, y en una batería
        compartida eso es peor que no tenerla. La propiedad se verifica igual,
        como assert del escenario de sucursales, donde sí tiene camino rojo.
        """
        self.assert_session_line_coverage(session, msg)
        self.assert_session_balances_consistent(session, msg)
