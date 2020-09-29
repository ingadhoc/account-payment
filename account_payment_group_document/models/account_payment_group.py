##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class AccountPaymentGroup(models.Model):

    _inherit = "account.payment.group"
    _order = "payment_date desc, name desc, id desc"
    _check_company_auto = True

    document_sequence_id = fields.Many2one(
        related='receiptbook_id.sequence_id',
    )
    receiptbook_id = fields.Many2one(
        'account.payment.receiptbook',
        'ReceiptBook',
        readonly=True,
        states={'draft': [('readonly', False)]},
        auto_join=True,
        check_company=True,
    )
    document_type_id = fields.Many2one(
        related='receiptbook_id.document_type_id',
    )
    next_number = fields.Integer(
        # related='receiptbook_id.sequence_id.number_next_actual',
        compute='_compute_next_number',
        string='Next Number',
    )
    # this field should be created on account_payment_document so that we have
    # a name if we don't work with account.document.type
    name = fields.Char(
        string='Document Reference',
        copy=False,
    )
    document_number = fields.Char(
        compute='_compute_document_number', inverse='_inverse_document_number',
        string='Document Number', readonly=True, states={'draft': [('readonly', False)]})

    _sql_constraints = [
        ('name_uniq', 'unique(name, receiptbook_id)',
            'Document number must be unique per receiptbook!')]

    @api.depends('name')
    def _compute_document_number(self):
        recs_with_name = self.filtered('name')
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

    @api.depends(
        'receiptbook_id.sequence_id.number_next_actual',
    )
    def _compute_next_number(self):
        """
        show next number only for payments without number and on draft state
        """
        for payment in self:
            if payment.state != 'draft' or not payment.receiptbook_id or payment.document_number:
                payment.next_number = False
                continue
            sequence = payment.receiptbook_id.sequence_id
            # we must check if sequence use date ranges
            if not sequence.use_date_range:
                payment.next_number = sequence.number_next_actual
            else:
                dt = self.payment_date or fields.Date.today()
                seq_date = self.env['ir.sequence.date_range'].search([
                    ('sequence_id', '=', sequence.id),
                    ('date_from', '<=', dt),
                    ('date_to', '>=', dt)], limit=1)
                if not seq_date:
                    seq_date = sequence._create_date_range_seq(dt)
                payment.next_number = seq_date.number_next_actual

    @api.constrains('company_id', 'partner_type')
    def _force_receiptbook(self):
        # we add cosntrins to fix odoo tests and also help in inmpo of data
        for rec in self:
            if not rec.receiptbook_id:
                rec.receiptbook_id = rec._get_receiptbook()

    @api.onchange('company_id', 'partner_type')
    def get_receiptbook(self):
        self.receiptbook_id = self._get_receiptbook()

    def _get_receiptbook(self):
        self.ensure_one()
        partner_type = self.partner_type or self._context.get(
            'partner_type', self._context.get('default_partner_type', False))
        receiptbook = self.env[
            'account.payment.receiptbook'].search([
                ('partner_type', '=', partner_type),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
        return receiptbook

    def post(self):
        for rec in self:
            if not rec.document_number:
                if rec.receiptbook_id and not rec.receiptbook_id.sequence_id:
                    raise UserError(_(
                        'Error!. Please define sequence on the receiptbook'
                        ' related documents to this payment or set the '
                        'document number.'))
                if rec.receiptbook_id.sequence_id:
                    rec.document_number = (
                        rec.receiptbook_id.with_context(
                            ir_sequence_date=rec.payment_date
                        ).sequence_id.next_by_id())
            rec.payment_ids.move_name = rec.name

            # hacemos el llamado acá y no arriba para primero hacer los checks
            # y ademas primero limpiar o copiar talonario antes de postear.
            # lo hacemos antes de mandar email asi sale correctamente numerado
            # necesitamos realmente mandar el tipo de documento? lo necesitamos para algo?
            super(AccountPaymentGroup, self.with_context(
                default_l10n_latam_document_type_id=rec.document_type_id.id)).post()
            if not rec.receiptbook_id:
                rec.name = any(
                    rec.payment_ids.mapped('name')) and ', '.join(
                    rec.payment_ids.mapped('name')) or False

        for rec in self:
            if rec.receiptbook_id.mail_template_id:
                rec.message_post_with_template(
                    rec.receiptbook_id.mail_template_id.id,
                )
        return True
