##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""Everything that reads ``l10n_latam.check.outstanding_line_id`` downstream.

These are the places that silently change meaning when the liquidity line of a
check payment moves (split move -> line inside the payment move) or when third
party checks start carrying an outstanding line. Part of the harness of task
70884.
"""

from odoo import fields
from odoo.tests import tagged

from .common import LatamCheckCommon


@tagged("post_install", "-at_install")
class TestChecksToDateReport(LatamCheckCommon):
    """``account.check.to_date.report.wizard`` reads outstanding_line_id in raw SQL."""

    def setUp(self):
        super().setUp()
        self.report = self.env["account.check.to_date.report.wizard"]
        self.tomorrow = fields.Date.add(self.today, days=1)

    def _handed(self, journal=None, to_date=None):
        # the report runs raw SQL, so pending ORM values must hit the database
        self.env.flush_all()
        return self.report._get_checks_handed((journal or self.bank_journal).id, to_date or self.tomorrow)

    def _on_hand(self, journal=None, to_date=None):
        self.env.flush_all()
        return self.report._get_checks_on_hand((journal or self.third_party_journal).id, to_date or self.tomorrow)

    def _debit(self, check, date):
        wizard = (
            self.env["account.check.action.wizard"]
            .with_context(active_model="l10n_latam.check", active_ids=check.ids)
            .create({"date": date})
        )
        wizard.action_confirm()

    def test_only_handed_checks_are_listed(self):
        """El reporte lista un renglon por cheque entregado, deja afuera los
        borradores y los anulados, y el QWeb los imprime."""
        handed = self._create_own_check_payment([20, 30, 70], numbers=["00020001", "00020002", "00020003"])
        handed.action_post()
        voided = self._create_own_check_payment([50], numbers=["00020401"])
        voided.action_post()
        voided.l10n_latam_new_check_ids.action_void()
        draft = self._create_own_check_payment([50], numbers=["00020301"])

        reported = self._handed()

        self.assertEqual(
            handed.l10n_latam_new_check_ids,
            reported & handed.l10n_latam_new_check_ids,
            "Every handed check must show up in the report",
        )
        self.assertNotIn(voided.l10n_latam_new_check_ids, reported)
        self.assertNotIn(draft.l10n_latam_new_check_ids, reported)

        wizard = self.report.create({"journal_id": self.bank_journal.id, "to_date": self.tomorrow})
        self.env.flush_all()
        report = self.env.ref("l10n_latam_check_ux.checks_to_date_report")
        html = report._render_qweb_html(report.report_name, wizard.ids)[0]
        self.assertIn(b"00020001", html)
        self.assertIn(b"00020002", html)
        self.assertNotIn(b"00020301", html, "A draft check must not be printed either")

    def test_the_report_date_decides_which_checks_are_still_handed(self):
        """Un cheque debitado antes de la fecha del reporte sale del listado;
        uno debitado despues seguia entregado a esa fecha, asi que queda."""
        payment = self._create_own_check_payment([20, 30, 70], numbers=["00020101", "00020102", "00020103"])
        payment.action_post()
        debited_now, debited_later, untouched = payment.l10n_latam_new_check_ids

        self._debit(debited_now, self.today)
        self._debit(debited_later, fields.Date.add(self.today, days=10))

        reported = self._handed()
        self.assertNotIn(debited_now, reported, "A debited check is no longer handed")
        self.assertEqual(
            debited_later + untouched,
            reported & payment.l10n_latam_new_check_ids,
            "A check debited after the report date was still handed at that date",
        )

    def test_third_party_checks_on_hand_until_deposited(self):
        payment = self._receive_third_party_checks([55, 45], numbers=["00020501", "00020502"])
        payment.action_post()
        checks = payment.l10n_latam_new_check_ids

        self.assertEqual(checks, self._on_hand() & checks, "Checks received and not yet moved are on hand")

        wizard = (
            self.env["l10n_latam.payment.mass.transfer"]
            .with_context(active_model="l10n_latam.check", active_ids=checks.ids)
            .create(
                {
                    "journal_id": self.third_party_journal.id,
                    "destination_journal_id": self.bank_journal.id,
                    "payment_date": self.today,
                }
            )
        )
        wizard._create_payments()

        self.assertFalse(self._on_hand() & checks, "Deposited checks left the third party journal")


@tagged("post_install", "-at_install")
class TestOutstandingAccountConsumers(LatamCheckCommon):
    """Other places that walk ``outstanding_line_id``."""

    def test_toggling_reconcile_on_the_account_recomputes_issue_state(self):
        """``account.account.write`` recomputes the issue_state of the checks
        whose outstanding line sits on that account."""
        payment = self._create_own_check_payment([20, 30], numbers=["00021001", "00021002"])
        payment.action_post()
        self.assertEqual(payment.l10n_latam_new_check_ids.mapped("issue_state"), ["handed", "handed"])

        self.deferred_check_account.write({"reconcile": False})
        self.assertEqual(
            payment.l10n_latam_new_check_ids.mapped("issue_state"),
            ["debited", "debited"],
            "Without reconciliation there is nothing left to debit",
        )

        self.deferred_check_account.write({"reconcile": True})
        self.assertEqual(payment.l10n_latam_new_check_ids.mapped("issue_state"), ["handed", "handed"])

    def test_partner_credit_includes_deferred_third_party_checks(self):
        """``res.partner.add_check_credit`` counts checks on hand not yet due."""
        self.partner.add_check_credit = True
        payment = self._receive_third_party_checks([55], numbers=["00021301"])
        payment.l10n_latam_new_check_ids.payment_date = fields.Date.add(self.today, days=30)
        payment.action_post()

        credit_with_checks = self.partner.with_company(self.company).credit
        self.partner.add_check_credit = False
        self.partner.invalidate_recordset(["credit"])
        credit_without_checks = self.partner.with_company(self.company).credit

        self.assertEqual(
            credit_with_checks - credit_without_checks, 55.0, "The deferred check must add up to the partner credit"
        )
