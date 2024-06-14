from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    receiptbook_id = fields.Many2one(
        'account.payment.receiptbook',
        'ReceiptBook',
        readonly=True,
        auto_join=True,
        check_company=True,
        compute='_compute_receiptbook',
        store=True,
        domain="[('partner_type', '=', partner_type)]",
    )

    def action_post(self):
        # si no tengo nombre y tengo talonario de recibo, numeramos con el talonario
        for rec in self.filtered(
                lambda x: x.receiptbook_id and (not x.name or x.name == '/' or not x.move_id._get_last_sequence())):
            if not rec.receiptbook_id.sequence_id:
                raise ValidationError(_(
                    'Error!. Please define sequence on the receiptbook related documents to this payment.'))

            rec.l10n_latam_document_type_id = rec.receiptbook_id.document_type_id.id
            name = rec.receiptbook_id.with_context(ir_sequence_date=rec.date).sequence_id.next_by_id()
            rec.name = "%s %s" % (rec.l10n_latam_document_type_id.doc_code_prefix, name)

        res = super().action_post()

        for rec in self.filtered('receiptbook_id.mail_template_id'):
            rec.message_post_with_source(
                rec.receiptbook_id.mail_template_id,
                subtype_xmlid='mail.mt_comment'
            )
        return res

    @api.depends('company_id', 'partner_type', 'is_internal_transfer')
    def _compute_receiptbook(self):
        for rec in self:
            if rec.is_internal_transfer:
                rec.receiptbook_id = False
            elif not rec.receiptbook_id or rec.receiptbook_id.company_id != rec.company_id:
                partner_type = rec.partner_type or self._context.get(
                    'partner_type', self._context.get('default_partner_type', False))
                receiptbook = self.env[
                    'account.payment.receiptbook'].search([
                        ('partner_type', '=', partner_type),
                        ('company_id', '=', rec.company_id.id),
                    ], limit=1)
                rec.receiptbook_id = receiptbook
