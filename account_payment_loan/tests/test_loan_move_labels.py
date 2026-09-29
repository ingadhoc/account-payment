from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestLoanMoveLabels(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("es_419")
        cls.env = cls.env(context=dict(cls.env.context, lang="es_419"))
        cls.loan_journal = cls.company_data["company"].loan_journal_id
        cls.card = cls.env["account.card"].create(
            {
                "name": "Préstamos",
                "is_loan": True,
                "loan_due_method": "create_day",
                "installment_ids": [
                    Command.create({"name": "3", "divisor": 3, "surcharge_coefficient": 1.2}),
                ],
            }
        )

    def _register_loan(self, context):
        wizard = (
            self.env["account.loan.register"]
            .with_context(**context)
            .create({"card_id": self.card.id, "installment_id": self.card.installment_ids.id})
        )
        # same button the wizard view shows for each case
        if wizard.refinancial_loan_move_ids:
            wizard.action_refinancial_loan()
        else:
            wizard.action_register_loan()
        return self.env["account.move"].search(
            [("journal_id", "=", self.loan_journal.id), ("partner_id", "=", self.partner_a.id)],
            order="id desc",
            limit=1,
        )

    def _installment_lines(self, loan):
        return loan.line_ids.filtered("date_maturity").sorted("date_maturity")

    def _loan_from_invoice(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_line_ids": [
                    Command.create({"name": "test", "quantity": 1, "price_unit": 1000.0, "tax_ids": []}),
                ],
            }
        )
        invoice.action_post()
        receivable = invoice.line_ids.filtered(lambda x: x.account_id.account_type == "asset_receivable")
        return invoice, self._register_loan({"active_ids": receivable.ids})

    def test_loan_from_invoice(self):
        """The loan points to the invoice it pays, in Spanish and without the due date on the label."""
        invoice, loan = self._loan_from_invoice()
        self.assertEqual(loan.ref, f"Préstamo de {invoice.name}")
        installments = self._installment_lines(loan)
        self.assertEqual(installments.mapped("name"), [f"{invoice.name} | Cuota {n}" for n in (1, 2, 3)])
        # the due date is still on the line, just not on the label
        self.assertTrue(all(installments.mapped("date_maturity")))
        self.assertEqual(sum(installments.mapped("debit")), 1200.0)
        self.assertEqual((loan.line_ids - installments).mapped("name"), ["Crédito", "Recargo financiero"])

    def test_refinancing(self):
        """The refinancing points to the loan it cancels, not to the extra charges refinanced with it."""
        _invoice, loan = self._loan_from_invoice()
        extra_charges = self.env["account.loan.extra.charges"].create(
            {"partner_id": self.partner_a.id, "loan_move_id": loan.id, "extra_charges": 50.0}
        )
        extra_charges.action_add_extra_charges()
        extra_move = self.env["account.move"].search(
            [("journal_id", "=", self.loan_journal.id), ("loan_move_ids", "in", loan.ids)]
        )
        self.assertEqual(extra_move.ref, f"Cargos extra del préstamo {loan.name}")
        self.assertEqual(extra_move.line_ids.mapped("name"), ["Cargos extra", "Cargos extra"])

        debt_report = self.env["account.loan.debt.report"].create({"partner_id": self.partner_a.id})
        self.assertEqual(debt_report.available_loan_move_ids, loan | extra_move)
        refinancing = self._register_loan(debt_report.action_refinancial_loan()["context"])
        self.assertEqual(refinancing.ref, f"Refinanciación de {loan.name}")
        installments = self._installment_lines(refinancing)
        self.assertEqual(installments.mapped("name"), [f"{loan.name} | Cuota {n}" for n in (1, 2, 3)])
        self.assertEqual(sum(installments.mapped("debit")), (1200.0 + 50.0) * 1.2)
