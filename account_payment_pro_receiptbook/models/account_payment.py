from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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

            if not rec.name or rec.name == "/":
                name = rec.receiptbook_id.with_context(ir_sequence_date=rec.date).sequence_id.next_by_id()
                rec.name = "%s %s" % (rec.receiptbook_id.document_type_id.doc_code_prefix, name)

        res = super().action_post()
        # Reincorporamos el seteo del l10n_latam_document_type_id para el caso de usar talonario de recibo
        # Ya que debido al fix en
        # https://github.com/ingadhoc/account-payment/commit/8a6ff0564d3526ec8ead24c90a8e53267d038f6a
        # se esta evitando el recomputo para impedir que este vuelva a False.
        for rec in self.filtered(lambda x: x.receiptbook_id):
            rec.move_id.l10n_latam_document_type_id = rec.receiptbook_id.document_type_id.id

        for rec in self.filtered("receiptbook_id.mail_template_id"):
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

    @api.depends()
    def _compute_name(self):
        super(
            AccountPayment, self.filtered(lambda x: not x.move_id or x.move_id.state != "draft" or not x.receiptbook_id)
        )._compute_name()
