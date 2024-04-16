from odoo import models, fields, api, Command, _
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
    )
    document_sequence_id = fields.Many2one(related='receiptbook_id.sequence_id',)
    sequence_type = fields.Selection(related='receiptbook_id.sequence_type',)
    document_type_id = fields.Many2one(related='receiptbook_id.document_type_id',)
    document_number = fields.Char(
        compute='_compute_document_number', inverse='_inverse_document_number',
        string='Document Number', readonly=True, copy=False)

    def action_post(self):

        for rec in self.filtered(lambda x: not x.is_internal_transfer):
            if not rec.document_number:
                if rec.receiptbook_id and not rec.receiptbook_id.sequence_id:
                    raise ValidationError(_(
                        'Error!. Please define sequence on the receiptbook'
                        ' related documents to this payment or set the '
                        'document number.'))

                rec.l10n_latam_document_type_id = rec.document_type_id.id
                if not rec.document_number:
                    document_number = (
                        rec.receiptbook_id.with_context(
                            ir_sequence_date=rec.date
                        ).sequence_id.next_by_id())
                    rec.document_number = rec.document_type_id._format_document_number(document_number)
                rec.name = "%s %s" % (rec.document_type_id.doc_code_prefix, document_number)

        if rec.receiptbook_id.mail_template_id:
            rec.message_post_with_source(rec.receiptbook_id.mail_template_id)

        return super().action_post()

    @api.depends('name')
    def _compute_document_number(self):

        recs_with_name = self.filtered(lambda x: x.name and x.name != '/' and x.name != '')
        for rec in recs_with_name:
            name = rec.name
            doc_code_prefix = rec.document_type_id.doc_code_prefix
            if doc_code_prefix and name:
                name = name.split(" ", 1)[-1]
            rec.document_number = name
        remaining = self - recs_with_name
        remaining.document_number = False

    @api.onchange('document_type_id', 'document_number')
    def _inverse_document_number(self):
        for rec in self.filtered('document_type_id'):
            if not rec.document_number:
                rec.name = False
            else:
                document_number = rec.document_type_id._format_document_number(rec.document_number)
                if rec.document_number != document_number:
                    rec.document_number = document_number
                rec.name = "%s %s" % (rec.document_type_id.doc_code_prefix, document_number)

    @api.depends('company_id', 'partner_type', 'is_internal_transfer')
    def _compute_receiptbook(self):
        for rec in self.filtered(lambda x: not x.receiptbook_id or x.receiptbook_id.company_id != x.company_id):
            if self.is_internal_transfer:
                rec.receiptbook_id = False
                continue
            partner_type = rec.partner_type or self._context.get(
                'partner_type', self._context.get('default_partner_type', False))
            receiptbook = self.env[
                'account.payment.receiptbook'].search([
                    ('partner_type', '=', partner_type),
                    ('company_id', '=', rec.company_id.id),
                ], limit=1)
            rec.receiptbook_id = receiptbook
                