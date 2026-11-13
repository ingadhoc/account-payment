##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import Command
from odoo.tests import tagged

from .common import EarlyDiscountCommon


@tagged("post_install", "-at_install")
class TestEarlyDiscountCreditNote(EarlyDiscountCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        tax = cls.env["account.tax"]
        cls.vat_21 = tax.create({"name": "VAT 21% ED", "amount": 21, "type_tax_use": "sale"})
        cls.vat_105 = tax.create({"name": "VAT 10.5% ED", "amount": 10.5, "type_tax_use": "sale"})
        cls.perception = tax.create({"name": "Perception 3% ED", "amount": 3, "type_tax_use": "sale"})

    def _create_taxed_invoice(self):
        return self._create_invoice(
            self.today,
            lines=[
                {
                    "name": "A",
                    "quantity": 1,
                    "price_unit": 1000,
                    "tax_ids": [Command.set((self.vat_21 + self.perception).ids)],
                },
                {"name": "B", "quantity": 1, "price_unit": 500, "tax_ids": [Command.set(self.vat_105.ids)]},
                {
                    "name": "C",
                    "quantity": 2,
                    "price_unit": 100,
                    "tax_ids": [Command.set((self.vat_21 + self.perception).ids)],
                },
            ],
        )

    def test_credit_note_lines(self):
        invoice = self._create_taxed_invoice()
        credit_note = invoice._create_early_discount_credit_note()

        self.assertEqual(credit_note.move_type, "out_refund")
        self.assertEqual(credit_note.state, "draft")
        self.assertEqual(credit_note.date, self.today)
        self.assertEqual(credit_note.reversed_entry_id, invoice)
        self.assertTrue(credit_note.is_early_discount)
        self.assertFalse(credit_note.invoice_payment_term_id)

        lines = credit_note.invoice_line_ids
        self.assertEqual(len(lines), 2, "one line per set of taxes")
        self.assertEqual(lines.account_id, self.company.account_journal_early_pay_discount_loss_account_id)
        line_21 = lines.filtered(lambda line: line.tax_ids == self.vat_21 + self.perception)
        line_105 = lines.filtered(lambda line: line.tax_ids == self.vat_105)
        self.assertAlmostEqual(line_21.price_subtotal, 60)
        self.assertAlmostEqual(line_105.price_subtotal, 25)

        # VAT and perceptions are refunded in the same proportion as the base
        self.assertAlmostEqual(credit_note.amount_untaxed, invoice.amount_untaxed * 0.05)
        self.assertAlmostEqual(credit_note.amount_total, invoice.amount_total * 0.05, delta=0.01)

    def test_credit_note_price_included_tax(self):
        vat_21_included = self.vat_21.copy({"name": "VAT 21% included ED", "price_include_override": "tax_included"})
        invoice = self._create_invoice(
            self.today,
            lines=[{"name": "A", "quantity": 1, "price_unit": 121000, "tax_ids": [Command.set(vat_21_included.ids)]}],
        )
        credit_note = invoice._create_early_discount_credit_note()
        self.assertAlmostEqual(credit_note.amount_untaxed, 5000)
        self.assertAlmostEqual(credit_note.amount_tax, 1050)
        self.assertAlmostEqual(credit_note.amount_total, 6050)

    def test_credit_note_perception_minimum_base(self):
        # the perception charged on the invoice is refunded although the credit note base is under the minimum
        if "l10n_ar_base_minimum_threshold" not in self.env["account.tax"]._fields:
            self.skipTest("Argentinian taxes not installed")
        if self.company.account_fiscal_country_id.code != "AR":
            self.skipTest("Company is not Argentinian")
        perception = self.perception.copy(
            {
                "name": "Perception 3% minimum ED",
                "country_id": self.env.ref("base.ar").id,
                "l10n_ar_state_id": self.env.ref("base.state_ar_c").id,
                "l10n_ar_base_minimum_threshold": 50000,
            }
        )
        invoice = self._create_invoice(
            self.today,
            lines=[
                {
                    "name": "A",
                    "quantity": 1,
                    "price_unit": 100000,
                    "tax_ids": [Command.set((self.vat_21 + perception).ids)],
                }
            ],
        )
        self.assertAlmostEqual(invoice.amount_total, 124000)
        credit_note = invoice._create_early_discount_credit_note()
        self.assertAlmostEqual(credit_note.amount_untaxed, 5000)
        self.assertAlmostEqual(credit_note.amount_tax, 1200)
        self.assertAlmostEqual(credit_note.amount_total, invoice.amount_total * 0.05)

    def test_credit_note_after_linked_regular_credit_note(self):
        # the discount is computed on what is owed after a regular credit note linked to the invoice
        invoice = self._create_invoice(
            self.today,
            lines=[{"name": "A", "quantity": 1, "price_unit": 1000, "tax_ids": [Command.set(self.vat_21.ids)]}],
        )
        regular = self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "partner_id": self.partner.id,
                "journal_id": self.sale_journal.id,
                "invoice_date": self.today,
                "reversed_entry_id": invoice.id,
                "invoice_line_ids": [
                    Command.create(
                        {"name": "Refund", "quantity": 1, "price_unit": 100, "tax_ids": [Command.set(self.vat_21.ids)]}
                    )
                ],
            }
        )
        regular.action_post()
        self.assertAlmostEqual(invoice._get_early_discount_amount(), 54.45)
        credit_note = invoice._create_early_discount_credit_note()
        self.assertAlmostEqual(credit_note.amount_untaxed, 45)
        self.assertAlmostEqual(credit_note.amount_tax, 9.45)
        self.assertAlmostEqual(credit_note.amount_total, 54.45)

    def test_post_credit_note(self):
        invoice = self._create_taxed_invoice()
        credit_note = invoice._create_early_discount_credit_note()
        credit_note._post_early_discount_credit_note()
        self.assertEqual(credit_note.state, "posted")

    def test_credit_note_document_type(self):
        if "l10n_ar_afip_pos_system" not in self.env["account.journal"]._fields:
            self.skipTest("Argentinian localization not installed")
        if self.company.account_fiscal_country_id.code != "AR":
            self.skipTest("Company is not Argentinian")
        journal = self.env["account.journal"].create(
            {
                "name": "Sales AR ED",
                "code": "ARED",
                "type": "sale",
                "l10n_latam_use_documents": True,
                "l10n_ar_afip_pos_number": 9001,
                "l10n_ar_afip_pos_system": "II_IM",
                "l10n_ar_afip_pos_partner_id": self.company.partner_id.id,
            }
        )
        self.partner.write(
            {
                "country_id": self.env.ref("base.ar").id,
                "l10n_latam_identification_type_id": self.env.ref("l10n_ar.it_cuit").id,
                "vat": "30712345671",
                "l10n_ar_afip_responsibility_type_id": self.env.ref("l10n_ar.res_IVARI").id,
            }
        )
        vat_21 = self.env["account.tax"].search(
            [
                ("company_id", "=", self.company.id),
                ("type_tax_use", "=", "sale"),
                ("amount_type", "=", "percent"),
                ("amount", "=", 21),
                ("tax_group_id.l10n_ar_vat_afip_code", "!=", False),
            ],
            limit=1,
        )
        invoice = self._create_invoice(
            self.today,
            lines=[{"name": "A", "quantity": 1, "price_unit": 1000, "tax_ids": [Command.set(vat_21.ids)]}],
            journal_id=journal.id,
        )
        credit_note = invoice._create_early_discount_credit_note()
        credit_note._post_early_discount_credit_note()

        invoice_document = invoice.l10n_latam_document_type_id
        credit_note_document = credit_note.l10n_latam_document_type_id
        self.assertEqual(credit_note.journal_id, journal)
        self.assertEqual(credit_note_document.internal_type, "credit_note")
        self.assertEqual(credit_note_document.l10n_ar_letter, invoice_document.l10n_ar_letter)
        self.assertTrue(credit_note.l10n_latam_document_number)
