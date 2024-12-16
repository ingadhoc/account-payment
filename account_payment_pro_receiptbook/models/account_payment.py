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
    # reescribimos este campo que se hereda desde account move para que refresque en la ui el cambio de talonario
    l10n_latam_manual_document_number = fields.Boolean(compute='_compute_l10n_latam_manual_document_number', string='Manual Number')
    # re escribimos tambien este campo para implementar el inverse que:
    # a) usa receiptbook_id.document_type_id en vez de l10n_latam_document_type_id
    # b) refresque ui ya que el otro metodo es del move
    l10n_latam_document_number = fields.Char(
        compute='_compute_l10n_latam_document_number', inverse='_inverse_l10n_latam_document_number',
        string='Document Number', readonly=False)

    def _compute_l10n_latam_document_number(self):
        # No podemos usar este approach de abajo porque actualmente estamos escribiendo el l10n_latam_document_type_id
        # recien en el post y entonces termina agregando un prefix de mas
        # todo esto igual la idea es re-factorizarlo y simplificarlo
        # for rec in self:
        #     rec.l10n_latam_document_number = rec.move_id.l10n_latam_document_number
        recs_with_name = self.filtered(lambda x: x.name != '/')
        for rec in recs_with_name:
            name = rec.name
            doc_code_prefix = rec.receiptbook_id.document_type_id.doc_code_prefix
            if doc_code_prefix and name:
                name = name.split(" ", 1)[-1]
            rec.l10n_latam_document_number = name
        remaining = self - recs_with_name
        remaining.l10n_latam_document_number = False

    @api.onchange('receiptbook_id', 'l10n_latam_document_number')
    def _inverse_l10n_latam_document_number(self):
        for rec in self.filtered(lambda x: x.receiptbook_id.document_type_id):
            if not rec.l10n_latam_document_number:
                rec.move_id.name = '/'
            else:
                # Para que este tipo de documento ayude a formatear números en talonarios manuales es necesario
                # que el document_type_id tenga país y por defecto los estamos creando sin. Ver mas info en commit message
                l10n_latam_document_number = rec.receiptbook_id.document_type_id._format_document_number(rec.l10n_latam_document_number)
                if rec.l10n_latam_document_number != l10n_latam_document_number:
                    rec.l10n_latam_document_number = l10n_latam_document_number
                rec.move_id.name = "%s %s" % (rec.receiptbook_id.document_type_id.doc_code_prefix, l10n_latam_document_number)

    @api.depends('receiptbook_id')
    def _compute_l10n_latam_manual_document_number(self):
        # no lo hacemos en _is_manual_document_number porque antes _compute_l10n_latam_manual_document_number filtra por diarios
        # que usen documentos y en pagos no usamos ese booleano
        manual_receipbook = self.filtered(lambda x: x.receiptbook_id and not x.receiptbook_id.sequence_id)
        manual_receipbook.l10n_latam_manual_document_number = True
        (self - manual_receipbook).l10n_latam_manual_document_number = False

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
