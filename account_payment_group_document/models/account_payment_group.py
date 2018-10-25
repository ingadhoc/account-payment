##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)


class AccountPaymentGroup(models.Model):
    _inherit = "account.payment.group"
    _order = "payment_date desc, document_number desc, id desc"

    document_number = fields.Char(
        string='Document Number',
        copy=False,
        readonly=True,
        states={'draft': [('readonly', False)]},
        track_visibility='always',
        index=True,
    )
    document_sequence_id = fields.Many2one(
        related='receiptbook_id.sequence_id',
        readonly=True,
    )
    localization = fields.Selection(
        related='company_id.localization',
        readonly=True,
    )
    # por ahora no agregamos esto, vamos a ver si alguien lo pide
    # manual_prefix = fields.Char(
    #     related='receiptbook_id.prefix',
    #     string='Prefix',
    #     readonly=True,
    #     copy=False
    # )
    # manual_sufix = fields.Integer(
    #     'Number',
    #     readonly=True,
    #     states={'draft': [('readonly', False)]},
    #     copy=False
    # )
    # TODO depreciate this field on v9
    # be care that sipreco project use it
    # force_number = fields.Char(
    #     'Force Number',
    #     readonly=True,
    #     states={'draft': [('readonly', False)]},
    #     copy=False
    # )
    receiptbook_id = fields.Many2one(
        'account.payment.receiptbook',
        'ReceiptBook',
        readonly=True,
        track_visibility='always',
        states={'draft': [('readonly', False)]},
        ondelete='restrict',
        auto_join=True,
    )
    document_type_id = fields.Many2one(
        related='receiptbook_id.document_type_id',
        readonly=True,
    )
    next_number = fields.Integer(
        # related='receiptbook_id.sequence_id.number_next_actual',
        compute='_compute_next_number',
        string='Next Number',
    )
    name = fields.Char(
        compute='_compute_name',
        string='Document Reference',
        store=True,
        index=True,
    )

    _sql_constraints = [
        ('document_number_uniq', 'unique(document_number, receiptbook_id)',
            'Document number must be unique per receiptbook!')]

    @api.multi
    @api.depends(
        'receiptbook_id.sequence_id.number_next_actual',
    )
    def _compute_next_number(self):
        """
        show next number only for payments without number and on draft state
        """
        for payment in self.filtered(
            lambda x: x.state == 'draft' and x.receiptbook_id and
                not x.document_number):
            sequence = payment.receiptbook_id.sequence_id
            # we must check if sequence use date ranges
            if not sequence.use_date_range:
                payment.next_number = sequence.number_next_actual
            else:
                dt = fields.Date.today()
                if self.env.context.get('ir_sequence_date'):
                    dt = self.env.context.get('ir_sequence_date')
                seq_date = self.env['ir.sequence.date_range'].search([
                    ('sequence_id', '=', sequence.id),
                    ('date_from', '<=', dt),
                    ('date_to', '>=', dt)], limit=1)
                if not seq_date:
                    seq_date = sequence._create_date_range_seq(dt)
                payment.next_number = seq_date.number_next_actual

    @api.multi
    @api.depends(
        # 'move_name',
        'state',
        'document_number',
        'document_type_id.doc_code_prefix'
    )
    def _compute_name(self):
        """
        * If document number and document type, we show them
        * Else, we show name
        """
        for rec in self:
            _logger.info('Getting name for payment group %s' % rec.id)
            if rec.state == 'posted':
                if rec.document_number and rec.document_type_id:
                    name = ("%s%s" % (
                        rec.document_type_id.doc_code_prefix or '',
                        rec.document_number))
                # for compatibility with v8 migration because receipbook
                # was not required and we dont have a name
                else:
                    name = ', '.join(rec.payment_ids.mapped('name'))
            else:
                name = _('Draft Payment')
            rec.name = name

    _sql_constraints = [
        ('name_uniq', 'unique(document_number, receiptbook_id)',
            'Document number must be unique per receiptbook!')]

    @api.multi
    @api.constrains('company_id', 'partner_type')
    def _force_receiptbook(self):
        # we add cosntrins to fix odoo tests and also help in inmpo of data
        for rec in self:
            if not rec.receiptbook_id:
                rec.receiptbook_id = rec._get_receiptbook()

    @api.onchange('company_id', 'partner_type')
    def get_receiptbook(self):
        self.receiptbook_id = self._get_receiptbook()

    @api.multi
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

    @api.multi
    def post(self):
        for rec in self:
            # si no ha receiptbook no exigimos el numero, esto por ej. lo
            # usa sipreco. Ademas limpiamos receiptbooks que se pueden
            # haber seteado en el pago
            if not rec.receiptbook_id:
                rec.payment_ids.write({
                    'receiptbook_id': False,
                })
                continue
            if not rec.document_number:
                if not rec.receiptbook_id.sequence_id:
                    raise UserError(_(
                        'Error!. Please define sequence on the receiptbook'
                        ' related documents to this payment or set the '
                        'document number.'))
                rec.document_number = (
                    rec.receiptbook_id.sequence_id.next_by_id())
            rec.payment_ids.write({
                'document_number': rec.document_number,
                'receiptbook_id': rec.receiptbook_id.id,
            })
            if rec.receiptbook_id.mail_template_id:
                rec.message_post_with_template(
                    rec.receiptbook_id.mail_template_id.id,
                )
        return super(AccountPaymentGroup, self).post()

    @api.multi
    @api.constrains('receiptbook_id', 'company_id')
    def _check_company_id(self):
        """
        Check receiptbook_id and voucher company
        """
        for rec in self:
            if (rec.receiptbook_id and
                    rec.receiptbook_id.company_id != rec.company_id):
                raise ValidationError(_(
                    'The company of the receiptbook and of the '
                    'payment must be the same!'))

    @api.multi
    @api.constrains('receiptbook_id', 'document_number')
    def validate_document_number(self):
        for rec in self:
            # if we have a sequence, number is set by sequence and we dont
            # check this
            if rec.document_sequence_id or not rec.document_number \
                    or not rec.receiptbook_id:
                continue
            # para usar el validator deberiamos extenderlo para que reciba
            # el registro o alguna referencia asi podemos obtener la data
            # del prefix y el padding del talonario de recibo
            res = rec.document_number
            padding = rec.receiptbook_id.padding
            res = '{:>0{padding}}'.format(res, padding=padding)

            prefix = rec.receiptbook_id.prefix
            if prefix and not res.startswith(prefix):
                res = prefix + res

            if res != rec.document_number:
                rec.document_number = res
