import base64

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import safe_eval


class AccountPayment(models.Model):
    _inherit = "account.payment"

    receiptbook_id = fields.Many2one(
        "account.payment.receiptbook",
        "ReceiptBook",
        readonly=True,
        auto_join=True,
        check_company=True,
        compute="_compute_receiptbook",
        store=True,
        domain="[('partner_type', '=', partner_type)]",
    )

    def action_post(self):
        # si no tengo nombre y tengo talonario de recibo, numeramos con el talonario
        for rec in self.filtered(
            lambda x: x.receiptbook_id
            and (not x.name or x.name == "/" or (x.move_id and not x.move_id._get_last_sequence()))
        ):
            if not rec.receiptbook_id.active:
                raise ValidationError(
                    _('Error! The receiptbook "%s" is archived. Please use a differente receipbook.')
                    % rec.receiptbook_id.name
                )
            if not rec.receiptbook_id.sequence_id:
                raise ValidationError(
                    _("Error!. Please define sequence on the receiptbook related documents to this payment.")
                )
            name = rec.receiptbook_id.with_context(ir_sequence_date=rec.date).sequence_id.next_by_id()
            rec.name = "%s %s" % (rec.receiptbook_id.document_type_id.doc_code_prefix, name)

        res = super().action_post()

        for rec in self.filtered("receiptbook_id.mail_template_id"):
            if rec.l10n_ar_withholding_ids:
                rec.receiptbook_id.mail_template_id.attachment_ids = rec.generate_withholding_reports()
            rec.message_post_with_source(rec.receiptbook_id.mail_template_id, subtype_xmlid="mail.mt_comment")
        return res

    @api.depends("company_id", "partner_type", "is_internal_transfer")
    def _compute_receiptbook(self):
        for rec in self:
            if rec.is_internal_transfer or not rec.company_id.use_receiptbook:
                rec.receiptbook_id = False
            elif not rec.receiptbook_id or rec.receiptbook_id.company_id != rec.company_id:
                partner_type = rec.partner_type or self._context.get(
                    "partner_type", self._context.get("default_partner_type", False)
                )
                receiptbook = self.env["account.payment.receiptbook"].search(
                    [
                        ("partner_type", "=", partner_type),
                        ("company_id", "=", rec.company_id.id),
                    ],
                    limit=1,
                )
                rec.receiptbook_id = receiptbook

    def generate_withholding_reports(self):
        self.ensure_one()
        attachments = []
        for line in self.l10n_ar_withholding_ids:
            action = self.env.ref("l10n_ar_tax.action_report_withholding_certificate")

            report_name = safe_eval.safe_eval(action.print_report_name, {"object": line.withholding_id})
            result, _ = self.env["ir.actions.report"]._render(action.report_name, line.withholding_id.id)
            file = base64.b64encode(result)

            attachment = self.env["ir.attachment"].create(
                {
                    "name": f"{report_name} - {line.tax_line_id.name}",
                    "mimetype": "application/pdf",
                    "datas": file,
                    "res_model": "account.payment",
                    "res_id": self.id,
                    "type": "binary",
                }
            )

            attachments.append(attachment.id)
        return attachments
