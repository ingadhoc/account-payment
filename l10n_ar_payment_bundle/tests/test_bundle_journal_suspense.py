# © 2026 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestBundleJournalSuspense(TransactionCase):
    """La creación del diario bundle no puede quedar bloqueada por la constraint de account_ux.

    El diario lo crea el post_init_hook y sus cuentas se arman en varios pasos dentro de la
    misma transacción, así que un estado intermedio puede dejar la cuenta pendiente igual a la
    transitoria de la compañía y hacer fallar la instalación entera del módulo. Ese flujo pasa
    `skip_suspense_outstanding_check` en el contexto; la edición manual del diario, no.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_payment_pro = True

        bundle_journal_id = cls.company._get_bundle_journal("inbound")
        if bundle_journal_id:
            cls.bundle_journal = cls.env["account.journal"].browse(bundle_journal_id)
        else:
            cls.bundle_journal = cls.env["account.journal"].create(
                {
                    "name": "Payment Bundle",
                    "type": "cash",
                    "code": "PBUN2",
                    "company_id": cls.company.id,
                    "inbound_payment_method_line_ids": [
                        Command.create(
                            {
                                "payment_method_id": cls.env.ref(
                                    "l10n_ar_payment_bundle.account_payment_in_payment_bundle"
                                ).id,
                            }
                        ),
                    ],
                }
            )

        cls.suspense_account = cls.env["account.account"].create(
            {
                "name": "Cuenta transitoria test",
                "code": "TSUSP",
                "account_type": "asset_current",
                "company_ids": [Command.link(cls.company.id)],
            }
        )

    def test_creation_flow_is_not_blocked(self):
        """Con el contexto del flujo de creación, la coincidencia no aborta la transacción."""
        journal = self.bundle_journal.with_context(skip_suspense_outstanding_check=True)
        journal.suspense_account_id = self.suspense_account
        journal.inbound_payment_method_line_ids.payment_account_id = self.suspense_account
        self.env.flush_all()

        self.assertEqual(
            journal.inbound_payment_method_line_ids.payment_account_id,
            journal.suspense_account_id,
        )

    def test_manual_edit_of_the_bundle_journal_is_still_blocked(self):
        """Sin ese contexto la validación sigue activa, también en el diario bundle."""
        self.bundle_journal.suspense_account_id = self.suspense_account

        with self.assertRaises(ValidationError):
            self.bundle_journal.inbound_payment_method_line_ids.payment_account_id = self.suspense_account
            self.env.flush_all()

    def test_manual_edit_of_a_regular_cash_journal_is_still_blocked(self):
        """Control: en un diario de efectivo común no cambia nada."""
        journal = self.env["account.journal"].create(
            {
                "name": "Caja Test Transitoria",
                "type": "cash",
                "code": "CSHTS",
                "company_id": self.company.id,
                "suspense_account_id": self.suspense_account.id,
            }
        )

        with self.assertRaises(ValidationError):
            journal.inbound_payment_method_line_ids.payment_account_id = self.suspense_account
            self.env.flush_all()
