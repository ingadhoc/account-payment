##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""Configuración de los escenarios de las suites de caja.

Separa las tres categorías de datos que las suites usan, que no son dos:

* **Entorno** — plan de cuentas y cuentas que la contabilidad necesita para
  existir. Sale de la base: recrearlo es caro, no aporta señal y nadie lo
  mantiene.
* **Configuración del escenario** — diarios, cajas, secuencias, usuarios,
  monedas. **La crea esta clase**, con ``.create()``. Es lo que decide qué se
  está probando, y crearla es lo que permite que la suite corra en cualquier
  base sin depender de qué localización esté instalada.
* **Documentos** — pagos, sesiones, asientos. **Siempre los crea el test**, que
  es lo que mide.

Por qué importa acá en particular: la base de un cliente (y la de demo) puede
tener cajas y sesiones abiertas propias. Si la suite se apoyara en ellas, un
assert como "esta sesión no está entre las disponibles" se degrada solo — para
que pase con datos ajenos alrededor, alguien lo reescribe como "hay al menos
una", y ese assert flojo es el que deja pasar incidentes en verde.

La aislación no se logra relajando asserts sino por construcción: todas las
cajas de la suite nacen con ``restrict_users=True`` y con **solo los usuarios de
la suite** permitidos, así las sesiones ajenas nunca entran en el dominio de
disponibles del usuario de test.
"""

from odoo import Command, fields
from odoo.tests import TransactionCase

from .invariants import CashboxInvariantsMixin


class CashboxCommon(CashboxInvariantsMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        cls.currency = cls.company.currency_id

        # Moneda propia de la suite, con cotización fija: no tocamos las tasas de
        # la base ni dependemos de que alguna moneda esté activa con cotización.
        cls.foreign_currency = cls.env["res.currency"].create(
            {"name": "TCB", "symbol": "TCB", "rounding": 0.01, "active": True}
        )
        cls.env["res.currency.rate"].create(
            {
                "currency_id": cls.foreign_currency.id,
                "rate": 2.0,  # 1 unidad de la moneda de la compañía = 2 TCB
                "company_id": cls.company.id,
                "name": fields.Date.context_today(cls.env["res.currency"]),
            }
        )

        cls.cashbox_user = cls._create_user("cashbox_operator", "Cashbox Operator")
        cls.viewer_user = cls._create_user("cashbox_viewer", "Cashbox Viewer")
        cls.other_user = cls._create_user("cashbox_other", "Cashbox Other")

        cls.partner = cls.env["res.partner"].create({"name": "Test Cashbox Partner"})

        cls.journal_cash = cls._create_journal("Test Cashbox Cash", "TCBC", "cash")
        cls.journal_bank = cls._create_journal("Test Cashbox Bank", "TCBB", "bank")

    # ------------------------------------------------------------------
    # configuración del escenario
    # ------------------------------------------------------------------
    @classmethod
    def _create_user(cls, login, name, groups=("base.group_user", "account.group_account_invoice")):
        return (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": name,
                    "login": login,
                    "company_id": cls.company.id,
                    "company_ids": [Command.set(cls.company.ids)],
                    "group_ids": [Command.set([cls.env.ref(g).id for g in groups])],
                }
            )
        )

    @classmethod
    def _create_journal(cls, name, code, journal_type="cash", currency=None):
        vals = {"name": name, "code": code, "type": journal_type, "company_id": cls.company.id}
        if currency:
            vals["currency_id"] = currency.id
        return cls.env["account.journal"].create(vals)

    @classmethod
    def _create_cashbox(cls, name, journals, **kwargs):
        """Caja de la suite. Restringida a los usuarios de la suite por default.

        La restricción es lo que aísla la suite de las cajas y sesiones que la
        base ya tenga: sin ella, una sesión ajena abierta entra en el dominio de
        sesiones disponibles y los asserts de disponibilidad dejan de significar
        lo que dicen.
        """
        users = kwargs.pop("users", None)
        if users is None:
            users = cls.cashbox_user | cls.viewer_user | cls.other_user
        vals = {
            "name": name,
            "company_id": cls.company.id,
            "journal_ids": [Command.set(journals.ids)],
            "restrict_users": True,
            "allowed_res_users_ids": [Command.set(users.ids)],
        }
        if not kwargs.get("allow_concurrent_sessions"):
            # sin sesiones concurrentes el nombre de la sesión lo pone la secuencia de la caja
            vals["sequence_id"] = (
                cls.env["ir.sequence"]
                .create(
                    {
                        "name": "Test Cashbox Sequence %s" % name,
                        "code": "account_cashbox_sequence",
                        "prefix": "%s-" % code_prefix(name),
                        "padding": 5,
                        "company_id": cls.company.id,
                    }
                )
                .id
            )
        vals.update(kwargs)
        return cls.env["account.cashbox"].create(vals)

    @classmethod
    def _create_account(cls, code, name, account_type, reconcile=False):
        return cls.env["account.account"].create(
            {
                "name": name,
                "code": code,
                "account_type": account_type,
                "reconcile": reconcile,
                "company_ids": [Command.set(cls.company.ids)],
            }
        )

    # ------------------------------------------------------------------
    # documentos
    # ------------------------------------------------------------------
    def _create_invoice(self, amount=100.0):
        """Factura de cliente mínima, sin producto: solo lo que el pago necesita."""
        income = self._create_account("TCBI", "Test Cashbox Income", "income")
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_date": fields.Date.context_today(self.env["account.move"]),
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Test Cashbox line",
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": income.id,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        return invoice

    def _create_session(self, cashbox, user=None, name=None, open_it=False, allowed_companies=None):
        """`allowed_companies` es necesario para cajas de otra compañía del árbol:
        la record rule de sesiones se evalúa contra las compañías habilitadas en
        el contexto, no contra las del usuario."""
        user = user or self.cashbox_user
        Session = self.env["account.cashbox.session"].with_user(user)
        if allowed_companies is not None:
            Session = Session.with_context(allowed_company_ids=allowed_companies.ids)
        vals = {"cashbox_id": cashbox.id, "user_ids": [Command.set(user.ids)]}
        if cashbox.allow_concurrent_sessions:
            # con sesiones concurrentes la secuencia no interviene: el nombre lo pone quien la crea
            vals["name"] = name or "Session %s/%s" % (cashbox.name, len(cashbox.session_ids) + 1)
        session = Session.create(vals)
        if open_it:
            session.action_account_cashbox_session_open()
        # se crea como el usuario (para ejercitar el ACL y el compute de user_ids) pero se
        # devuelve en el env de la suite: cada test declara con qué usuario opera
        return session.sudo().with_env(self.env)

    def _create_payment(self, journal, amount=100.0, session=None, user=None, post=True, **kwargs):
        user = user or self.cashbox_user
        vals = {
            "journal_id": journal.id,
            "amount": amount,
            "date": fields.Date.context_today(self.env["account.payment"]),
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": self.partner.id,
        }
        if session is not None:
            # session=False deja el pago explícitamente sin sesión: sin eso el compute le
            # asignaría la única sesión abierta y el escenario mediría otra cosa
            vals["cashbox_session_id"] = session.id if session else False
        vals.update(kwargs)
        payment = self.env["account.payment"].with_user(user).create(vals)
        if post:
            payment.action_post()
        return payment.sudo().with_env(self.env)


def code_prefix(name):
    """Prefijo de secuencia derivado del nombre de la caja, sin espacios."""
    return "".join(ch for ch in name.upper() if ch.isalnum())[:8]
