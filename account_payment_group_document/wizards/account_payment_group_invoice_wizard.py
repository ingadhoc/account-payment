##############################################################################
# For copyright and license notices, see __manifest__.py file in root directory
##############################################################################
from odoo import api, fields, models


class AccountPaymentGroupInvoiceWizard(models.TransientModel):
    _inherit = "account.payment.group.invoice.wizard"

    use_documents = fields.Boolean(
        related='journal_id.l10n_latam_use_documents',
        string='Use Documents?',
    )
    journal_document_type_id = fields.Many2one(
        'l10n_latam.document.type',
        'Document Type',
        ondelete='cascade',
    )
    document_sequence_id = fields.Many2one('ir.sequence', compute='_compute_l10n_latam_sequence')
    document_number = fields.Char(
        string='Document Number',
    )

    @api.depends('journal_document_type_id')
    def _compute_l10n_latam_sequence(self):
        for rec in self:
            refund = rec.env['account.move'].new({
                'type': self.get_invoice_vals().get('type'),
                'journal_id': rec.journal_id.id,
                'partner_id': rec.payment_group_id.partner_id.id,
                'company_id': rec.payment_group_id.company_id.id,
                'l10n_latam_document_type_id': rec.journal_document_type_id.id,
            })
            rec.document_sequence_id = refund._get_document_type_sequence()

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if self.journal_id.l10n_latam_use_documents:
            refund = self.env['account.move'].new({
                'type': self.get_invoice_vals().get('type'),
                'journal_id': self.journal_id.id,
                'partner_id': self.payment_group_id.partner_id.id,
                'company_id': self.payment_group_id.company_id.id,
            })
            self.journal_document_type_id = refund.l10n_latam_document_type_id
            return {'domain': {
                'journal_document_type_id': [('id', 'in', refund.l10n_latam_available_document_type_ids.ids)]}}

    def get_invoice_vals(self):
        invoice_vals = super(
            AccountPaymentGroupInvoiceWizard, self).get_invoice_vals()
        invoice_vals.update({
            'l10n_latam_document_type_id': self.journal_document_type_id.id,
            'l10n_latam_document_number': self.document_number,
        })
        return invoice_vals
