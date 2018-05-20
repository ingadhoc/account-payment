##############################################################################
# For copyright and license notices, see __manifest__.py file in root directory
##############################################################################
from odoo import api, fields, models


class AccountPaymentGroupInvoiceWizard(models.TransientModel):
    _inherit = "account.payment.group.invoice.wizard"

    use_documents = fields.Boolean(
        related='journal_id.use_documents',
        string='Use Documents?',
        readonly=True,
    )
    journal_document_type_id = fields.Many2one(
        'account.journal.document.type',
        'Document Type',
        ondelete='cascade',
    )
    document_sequence_id = fields.Many2one(
        related='journal_document_type_id.sequence_id',
        readonly=True,
    )
    document_number = fields.Char(
        string='Document Number',
    )
    available_journal_document_type_ids = fields.Many2many(
        'account.journal.document.type',
        compute='_compute_available_journal_document_types',
        string='Available Journal Document Types',
    )

    @api.multi
    @api.depends('journal_id')
    def _compute_available_journal_document_types(self):
        for rec in self:
            journal = rec.journal_id
            if not journal:
                return True
            invoice_type = self.get_invoice_vals().get('type')
            res = self.env[
                'account.invoice']._get_available_journal_document_types(
                    journal, invoice_type, self.payment_group_id.partner_id)
            rec.available_journal_document_type_ids = res[
                'available_journal_document_types']
            rec.journal_document_type_id = res[
                'journal_document_type']

    @api.multi
    def get_invoice_vals(self):
        invoice_vals = super(
            AccountPaymentGroupInvoiceWizard, self).get_invoice_vals()
        invoice_vals.update({
            'journal_document_type_id': self.journal_document_type_id.id,
            'document_number': self.document_number,
        })
        return invoice_vals
