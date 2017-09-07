# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in root directory
##############################################################################
from openerp import api, fields, models


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
    def onchange(self, values, field_name, field_onchange):
        """
        Idea obtenida de aca
        https://github.com/odoo/odoo/issues/16072#issuecomment-289833419
        por el cambio que se introdujo en esa mimsa conversación, TODO en v11
        no haría mas falta, simplemente domain="[('id', 'in', x2m_field)]"
        Otras posibilidades que probamos pero no resultaron del todo fue:
        * agregar onchange sobre campos calculados y que devuelvan un dict con
        domain. El tema es que si se entra a un registro guardado el onchange
        no se ejecuta
        * usae el modulo de web_domain_field que esta en un pr a la oca
        """
        for field in field_onchange.keys():
            if field.startswith('available_journal_document_type_ids.'):
                del field_onchange[field]
        return super(AccountPaymentGroupInvoiceWizard, self).onchange(
            values, field_name, field_onchange)

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
