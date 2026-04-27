import logging

from odoo import Command, api, fields, models

_logger = logging.getLogger(__name__)
# pylint: disable=consider-merging-classes-inherited


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @api.model
    def _install_l10n_ar_payment_bundle_demo(self, companies):
        """Crea data demo para argentina"""
        for company in companies.filtered(lambda x: x.country_code == "AR"):
            self = self.with_company(company)
            today = fields.Date.today()

            write_off_type = self._get_or_create_write_off_type(company)
            self._create_demo_supplier_invoice_with_writeoff(company, today, write_off_type)
            self._create_demo_supplier_invoice_with_linked_payments(company, today)
            self._create_demo_customer_invoice_with_linked_payments(company, today)

    def _get_or_create_write_off_type(self, company):
        write_off_account = self.env.ref(f"account.{company.id}_base_ajuste_por_redondeo", raise_if_not_found=False)
        if not write_off_account:
            return None
        write_off_type = self.env["account.write_off.type"].search(
            [("account_id", "=", write_off_account.id), ("name", "=", "Diferencia de cambio / ajuste")],
            limit=1,
        )
        if not write_off_type:
            write_off_type = self.env["account.write_off.type"].create(
                {
                    "name": "Diferencia de cambio / ajuste",
                    "account_id": write_off_account.id,
                }
            )
        return write_off_type

    def _create_demo_supplier_invoice_with_writeoff(self, company, today, write_off_type):
        if not write_off_type:
            return
        doc_type = self.env.ref("l10n_ar.dc_c_f")
        partner_adhoc = self.env.ref("l10n_ar.res_partner_adhoc")
        invoice = self.env["account.move"].search(
            [
                ("move_type", "=", "in_invoice"),
                ("company_id", "=", company.id),
                ("name", "like", "00001-00000099"),
                ("partner_id", "=", partner_adhoc.id),
            ],
            limit=1,
        )
        if not invoice:
            invoice = (
                self.env["account.move"]
                .with_context(skip_pdf_attachment_generation=True, skip_readonly_check=True)
                .create(
                    {
                        "move_type": "in_invoice",
                        "partner_id": partner_adhoc.id,
                        "currency_id": self.env.ref("base.ARS").id,
                        "invoice_date": today,
                        "l10n_latam_document_type_id": doc_type.id,
                        "l10n_latam_document_number": "0001-00000099",
                        "invoice_line_ids": [
                            Command.create(
                                {
                                    "product_id": self.env.ref("product.product_product_2").id,
                                    "quantity": 1,
                                    "price_unit": 10000,
                                    "tax_ids": [
                                        Command.set(
                                            [self.env.ref(f"account.{company.id}_ri_tax_vat_no_corresponde_ventas").id]
                                        )
                                    ],
                                }
                            )
                        ],
                        "company_id": company.id,
                    }
                )
            )
            if invoice.state == "draft":
                invoice.action_post()

        company._create_payment_bundle_journal_if_needed()
        bundle_journal = self.env["account.journal"].search(
            [
                ("outbound_payment_method_line_ids.payment_method_id.code", "=", "payment_bundle"),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        bundle_pml = bundle_journal.outbound_payment_method_line_ids.filtered(
            lambda l: l.payment_method_id.code == "payment_bundle"
        )
        bank_journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", company.id)], limit=1
        )
        if not bundle_pml or not bank_journal:
            _logger.warning(
                "l10n_ar_payment_bundle demo: bundle_journal=%s bundle_pml=%s bank_journal=%s — skipping company %s",
                bundle_journal,
                bundle_pml,
                bank_journal,
                company.name,
            )
            return
        invoice.flush_recordset()
        debt_line = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == "liability_payable" and l.amount_residual != 0
        )
        if not debt_line:
            return
        main_payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": partner_adhoc.id,
                "amount": 0,
                "journal_id": bundle_journal.id,
                "payment_method_line_id": bundle_pml.id,
                "date": today,
                "to_pay_move_line_ids": [Command.set(debt_line.ids)],
                "write_off_amount": 100,
                "write_off_type_id": write_off_type.id,
                "company_id": company.id,
            }
        )
        self.env["account.payment"].with_context(
            default_counterpart_currency_id=main_payment.counterpart_currency_id.id
        ).create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": partner_adhoc.id,
                "amount": 9900,
                "journal_id": bank_journal.id,
                "date": today,
                "main_payment_id": main_payment.id,
                "company_id": company.id,
            }
        )
        if main_payment.state == "draft":
            main_payment.action_post()

    def _create_demo_supplier_invoice_with_linked_payments(self, company, today):
        partner_gritti = self.env.ref("l10n_ar.res_partner_gritti_agrimensura")
        doc_type_b = self.env.ref("l10n_ar.dc_b_f", raise_if_not_found=False)
        customer_invoice = self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("company_id", "=", company.id),
                ("name", "like", "00002-00000001"),
                ("partner_id", "=", partner_gritti.id),
            ],
            limit=1,
        )
        if not customer_invoice:
            inv_vals = {
                "move_type": "out_invoice",
                "partner_id": partner_gritti.id,
                "currency_id": self.env.ref("base.ARS").id,
                "invoice_date": today,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.env.ref("product.product_product_2").id,
                            "quantity": 1,
                            "price_unit": 15000,
                            "tax_ids": [Command.set([self.env.ref(f"account.{company.id}_ri_tax_vat_21_ventas").id])],
                        }
                    )
                ],
                "company_id": company.id,
            }
            if doc_type_b:
                inv_vals["l10n_latam_document_type_id"] = doc_type_b.id
                inv_vals["l10n_latam_document_number"] = "0002-00000001"
                inv_vals["l10n_latam_document_type_id"] = doc_type_b.id
                inv_vals["l10n_latam_document_number"] = "0002-00000001"
            customer_invoice = (
                self.env["account.move"]
                .with_context(skip_pdf_attachment_generation=True, skip_readonly_check=True)
                .create(inv_vals)
            )
            if customer_invoice.state == "draft":
                customer_invoice.action_post()
        company._create_payment_bundle_journal_if_needed()
        bundle_journal = self.env["account.journal"].search(
            [
                ("outbound_payment_method_line_ids.payment_method_id.code", "=", "payment_bundle"),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        bundle_pml = bundle_journal.outbound_payment_method_line_ids.filtered(
            lambda l: l.payment_method_id.code == "payment_bundle"
        )
        bank_journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", company.id)], limit=1
        )
        customer_invoice.flush_recordset()
        debt_line2 = customer_invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == "liability_payable" and l.amount_residual != 0
        )
        if debt_line2 and bundle_pml and bank_journal:
            main_payment2 = self.env["account.payment"].create(
                {
                    "payment_type": "outbound",
                    "partner_type": "supplier",
                    "partner_id": partner_gritti.id,
                    "amount": 0,
                    "journal_id": bundle_journal.id,
                    "payment_method_line_id": bundle_pml.id,
                    "date": today,
                    "to_pay_move_line_ids": [Command.set(debt_line2.ids)],
                    "company_id": company.id,
                }
            )
            for linked_amount in [6000, 4000]:
                self.env["account.payment"].with_context(
                    default_counterpart_currency_id=main_payment2.counterpart_currency_id.id
                ).create(
                    {
                        "payment_type": "outbound",
                        "partner_type": "supplier",
                        "partner_id": partner_gritti.id,
                        "amount": linked_amount,
                        "journal_id": bank_journal.id,
                        "date": today,
                        "main_payment_id": main_payment2.id,
                        "company_id": company.id,
                    }
                )
            if main_payment2.state == "draft":
                main_payment2.action_post()

    def _create_demo_customer_invoice_with_linked_payments(self, company, today):
        partner_gritti = self.env.ref("l10n_ar.res_partner_gritti_agrimensura")
        company._create_payment_bundle_journal_if_needed()
        bundle_journal = self.env["account.journal"].search(
            [
                ("outbound_payment_method_line_ids.payment_method_id.code", "=", "payment_bundle"),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        bundle_pml_in = bundle_journal.inbound_payment_method_line_ids.filtered(
            lambda l: l.payment_method_id.code == "payment_bundle"
        )
        bank_journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", company.id)], limit=1
        )
        doc_type_b = self.env.ref("l10n_ar.dc_b_f", raise_if_not_found=False)
        customer_invoice = self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("company_id", "=", company.id),
                ("name", "like", "00002-00000001"),
                ("partner_id", "=", partner_gritti.id),
            ],
            limit=1,
        )
        if not customer_invoice:
            inv_vals = {
                "move_type": "out_invoice",
                "partner_id": partner_gritti.id,
                "currency_id": self.env.ref("base.ARS").id,
                "invoice_date": today,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.env.ref("product.product_product_2").id,
                            "quantity": 1,
                            "price_unit": 15000,
                            "tax_ids": [
                                Command.set([self.env.ref(f"account.{company.id}_ri_tax_vat_no_corresponde_ventas").id])
                            ],
                        }
                    )
                ],
                "company_id": company.id,
            }
            if doc_type_b:
                inv_vals["l10n_latam_document_type_id"] = doc_type_b.id
                inv_vals["l10n_latam_document_number"] = "0002-00000001"
            customer_invoice = (
                self.env["account.move"]
                .with_context(skip_pdf_attachment_generation=True, skip_readonly_check=True)
                .create(inv_vals)
            )
            if customer_invoice.state == "draft":
                customer_invoice.action_post()
        customer_invoice.flush_recordset()
        receivable_line = customer_invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable" and l.amount_residual != 0
        )
        if not receivable_line or not bundle_pml_in or not bank_journal:
            return
        main_payment3 = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": partner_gritti.id,
                "amount": 0,
                "journal_id": bundle_journal.id,
                "payment_method_line_id": bundle_pml_in.id,
                "date": today,
                "to_pay_move_line_ids": [Command.set(receivable_line.ids)],
                "company_id": company.id,
            }
        )
        for linked_amount in [10000, 5000]:
            self.env["account.payment"].with_context(
                default_counterpart_currency_id=main_payment3.counterpart_currency_id.id
            ).create(
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": partner_gritti.id,
                    "amount": linked_amount,
                    "journal_id": bank_journal.id,
                    "date": today,
                    "main_payment_id": main_payment3.id,
                    "company_id": company.id,
                }
            )
        if main_payment3.state == "draft":
            main_payment3.action_post()
