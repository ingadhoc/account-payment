##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import time

from odoo import Command
from odoo.addons.l10n_ar.tests.common import TestArCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestFinancialSurchargeBranch(TestArCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parent = cls.company_ri
        cls.branch = cls.env["res.company"].create(
            {
                "name": "(AR) Branch RI (Unit Tests)",
                "parent_id": cls.parent.id,
                "country_id": cls.parent.country_id.id,
                "l10n_ar_afip_start_date": time.strftime("%Y-01-01"),
            }
        )
        cls.branch.partner_id.write(
            {
                "l10n_ar_afip_responsibility_type_id": cls.env.ref("l10n_ar.res_IVARI").id,
                "l10n_latam_identification_type_id": cls.env.ref("l10n_ar.it_cuit").id,
                "vat": "30123456781",
            }
        )
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=(cls.branch + cls.parent).ids))
        cls.branch_sale_journal = cls._create_journal(
            "preprinted",
            {"company_id": cls.branch.id, "l10n_ar_afip_pos_partner_id": cls.branch.partner_id.id},
        )
        cls.branch_bank_journal = cls.env["account.journal"].create(
            {"name": "Branch Bank", "type": "bank", "code": "BRBNK", "company_id": cls.branch.id}
        )

        # the surcharge product only carries the VAT of the parent company
        cls.surcharge_product = cls.env["product.product"].create(
            {"name": "Financial Surcharge", "type": "service", "taxes_id": [Command.set(cls.tax_21.ids)]}
        )
        # the branch is created after the chart was loaded, so it gets no default accounts
        cls.res_partner_adhoc.with_company(cls.branch).property_account_receivable_id = cls.company_data[
            "default_account_receivable"
        ]
        for company in cls.parent + cls.branch:
            cls.surcharge_product.with_company(company).property_account_income_id = cls.company_data[
                "default_account_revenue"
            ]
        (cls.parent + cls.branch).product_surcharge_id = cls.surcharge_product

        cls.card = cls.env["account.card"].create({"name": "Test Card", "company_id": cls.parent.id})
        cls.installment = cls.env["account.card.installment"].create(
            {"card_id": cls.card.id, "name": "3", "divisor": 3, "installment": 3, "surcharge_coefficient": 1.10}
        )
        cls.method_line = cls.branch_bank_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "manual"
        )
        cls.method_line.available_card_ids = cls.card

    def test_branch_surcharge_uses_parent_tax(self):
        """A branch without its own VAT invoices the surcharge with the VAT of its parent company."""
        payment = (
            self.env["account.payment"]
            .with_company(self.branch)
            .create(
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": self.res_partner_adhoc.id,
                    "journal_id": self.branch_bank_journal.id,
                    "payment_method_line_id": self.method_line.id,
                    "card_id": self.card.id,
                    "installment_id": self.installment.id,
                    "amount": 110_000,
                }
            )
        )
        self.assertAlmostEqual(payment.financing_surcharge, 10_000, places=2)

        payment.action_post()

        debit_note = payment.to_pay_move_line_ids.move_id.filtered(
            lambda move: move.l10n_latam_document_type_id.internal_type == "debit_note"
        )
        self.assertEqual(debit_note.state, "posted")
        self.assertEqual(debit_note.journal_id, self.branch_sale_journal)
        self.assertEqual(debit_note.invoice_line_ids.tax_ids, self.tax_21)
        self.assertAlmostEqual(debit_note.amount_untaxed, 8_264.46, places=2)
        self.assertAlmostEqual(debit_note.amount_total, 10_000, places=2)
