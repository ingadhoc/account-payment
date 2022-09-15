##############################################################################
# For copyright and license notices, see __manifest__.py file in root directory
##############################################################################
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountPaymentGroupInvoiceWizard(models.TransientModel):
    _name = "account.payment.group.invoice.wizard"
    _description = "account.payment.group.invoice.wizard"

    @api.model
    def default_payment_group(self):
        return self.env['account.payment.group'].browse(
            self._context.get('active_id', False))

    payment_group_id = fields.Many2one(
        'account.payment.group',
        default=default_payment_group,
        ondelete='cascade',
        required=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        'Journal',
        required=True,
        ondelete='cascade',
    )
    invoice_date = fields.Date(
        string='Refund Date',
        default=fields.Date.context_today,
        required=True
    )
    currency_id = fields.Many2one(
        related='payment_group_id.currency_id',
    )
    date = fields.Date(
        string='Accounting Date'
    )
    product_id = fields.Many2one(
        'product.product',
        required=True,
        domain=[('sale_ok', '=', True)],
    )
    tax_ids = fields.Many2many(
        'account.tax',
        string='Taxes',
    )
    amount_untaxed = fields.Monetary(
        string='Untaxed Amount',
        required=True,
        compute='_compute_amount_untaxed',
        inverse='_inverse_amount_untaxed',
    )
    # we make amount total the main one and the other computed because the
    # normal case of use would be to know the total amount and also this amount
    # is the suggested one on creating the wizard
    amount_total = fields.Monetary(
        string='Total Amount',
        required=True
    )
    description = fields.Char(
        string='Reason',
    )
    company_id = fields.Many2one(
        related='payment_group_id.company_id',
    )
    account_analytic_id = fields.Many2one(
        'account.analytic.account',
        'Analytic Account',
    )

    use_documents = fields.Boolean(
        related='journal_id.l10n_latam_use_documents',
        string='Use Documents?',
    )
    journal_document_type_id = fields.Many2one(
        'l10n_latam.document.type',
        'Document Type',
        ondelete='cascade',
    )
    l10n_latam_manual_document_number = fields.Boolean(
        compute='_compute_l10n_latam_manual_document_number', string='Manual Number')
    document_number = fields.Char(
        string='Document Number',
    )

    @api.depends('journal_document_type_id')
    def _compute_l10n_latam_manual_document_number(self):
        for rec in self:
            refund = rec.env['account.move'].new({
                'move_type': self.get_invoice_vals().get('move_type'),
                'journal_id': rec.journal_id.id,
                'partner_id': rec.payment_group_id.partner_id.id,
                'company_id': rec.payment_group_id.company_id.id,
                'l10n_latam_document_type_id': rec.journal_document_type_id.id,
            })
            rec.l10n_latam_manual_document_number = refund._is_manual_document_number()

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if self.journal_id.l10n_latam_use_documents:
            refund = self.env['account.move'].new({
                'move_type': self.get_invoice_vals().get('move_type'),
                'journal_id': self.journal_id.id,
                'partner_id': self.payment_group_id.partner_id.id,
                'company_id': self.payment_group_id.company_id.id,
            })
            if self._context.get('internal_type') == 'debit_note':
                document_types = refund.l10n_latam_available_document_type_ids.filtered(lambda x: x.internal_type == 'debit_note')
                self.journal_document_type_id = document_types and document_types[0]._origin or refund.l10n_latam_document_type_id
            else:
                self.journal_document_type_id = refund.l10n_latam_document_type_id
            return {'domain': {
                'journal_document_type_id': [('id', 'in', refund.l10n_latam_available_document_type_ids.ids)]}}

    @api.onchange('product_id')
    def change_product(self):
        self.ensure_one()
        if self.payment_group_id.partner_type == 'supplier':
            taxes = self.product_id.supplier_taxes_id
        else:
            taxes = self.product_id.taxes_id
        company = self.company_id or self.env.company
        taxes = taxes.filtered(lambda r: r.company_id == company)
        self.tax_ids = self.payment_group_id.partner_id.with_company(
            company).property_account_position_id.map_tax(taxes)

    @api.onchange('amount_untaxed', 'tax_ids')
    def _inverse_amount_untaxed(self):
        self.ensure_one()
        if self.tax_ids:
            taxes = self.tax_ids.compute_all(
                self.amount_untaxed, self.company_id.currency_id, 1.0,
                product=self.product_id,
                partner=self.payment_group_id.partner_id)
            self.amount_total = taxes['total_included']
        else:
            self.amount_total = self.amount_untaxed

    @api.depends('tax_ids', 'amount_total')
    def _compute_amount_untaxed(self):
        """
        For now we implement inverse only for percent taxes. We could extend to
        other by simulating tax.price_include = True, computing tax and
        then restoring tax.price_include = False.
        """
        self.ensure_one()
        tax_percent = 0.0
        for tax in self.tax_ids.filtered(
                lambda x: not x.price_include):
            if tax.amount_type == 'percent':
                tax_percent += tax.amount
            elif tax.amount_type == 'partner_tax':
                # ugly compatibility with l10n_ar l10n_ar_account_withholding
                tax_percent += tax.get_partner_alicuot(
                    self.payment_group_id.partner_id,
                    fields.Date.context_today(self)).alicuota_percepcion
            else:
                raise ValidationError(_(
                    'You can only set amount total if taxes are of type '
                    'percentage'))
        total_percent = (1 + tax_percent / 100) or 1.0
        self.amount_untaxed = self.amount_total / total_percent

    @api.onchange('payment_group_id')
    def change_payment_group(self):
        journal_type = 'sale'
        type_tax_use = 'sale'
        if self.payment_group_id.partner_type == 'supplier':
            journal_type = 'purchase'
            type_tax_use = 'purchase'
        journal_domain = [
            ('type', '=', journal_type),
            ('company_id', '=', self.payment_group_id.company_id.id),
        ]
        tax_domain = [
            ('type_tax_use', '=', type_tax_use),
            ('company_id', '=', self.payment_group_id.company_id.id)]
        self.journal_id = self.env['account.journal'].search(
            journal_domain, limit=1)
        # usually debit/credit note will be for the payment difference
        self.amount_total = abs(self.payment_group_id.payment_difference)
        return {'domain': {
            'journal_id': journal_domain,
            'tax_ids': tax_domain,
        }}

    def get_invoice_vals(self):
        self.ensure_one()
        payment_group = self.payment_group_id
        if payment_group.partner_type == 'supplier':
            invoice_type = 'in_'
        else:
            invoice_type = 'out_'

        if self._context.get('refund'):
            invoice_type += 'refund'
        else:
            invoice_type += 'invoice'

        return {
            'ref': self.description,
            'date': self.date,
            'invoice_date': self.invoice_date,
            'invoice_origin': _('Payment id %s') % payment_group.id,
            'journal_id': self.journal_id.id,
            'invoice_user_id': payment_group.partner_id.user_id.id,
            'partner_id': payment_group.partner_id.id,
            'move_type': invoice_type,
            'l10n_latam_document_type_id': self.journal_document_type_id.id,
            'l10n_latam_document_number': self.document_number,
        }

    def confirm(self):
        self.ensure_one()

        self = self.with_company(self.company_id).with_context(company_id=self.company_id.id)
        invoice_vals = self.get_invoice_vals()
        line_vals = {
            'product_id': self.product_id.id,
            'price_unit': self.amount_untaxed,
            'tax_ids': [(6, 0, self.tax_ids.ids)],
        }
        if self.account_analytic_id:
            line_vals['analytic_account_id'] = self.account_analytic_id.id
        invoice_vals['invoice_line_ids'] = [(0, 0, line_vals)]
        invoice = self.env['account.move'].create(invoice_vals)
        invoice.action_post()

        self.payment_group_id.to_pay_move_line_ids += (invoice.open_move_line_ids)

    @api.onchange('document_number', 'journal_document_type_id')
    def _onchange_document_number(self):
        if self.journal_document_type_id:
            document_number = self.journal_document_type_id._format_document_number(
                self.document_number)
            if self.document_number != document_number:
                self.document_number = document_number
