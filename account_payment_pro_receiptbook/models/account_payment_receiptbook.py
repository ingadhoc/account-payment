##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPaymentReceiptbook(models.Model):
    """
    account.payment.receiptbook: analogo a account.journal.document.type pero para pagos
    """

    _name = "account.payment.receiptbook"
    _description = "Account payment Receiptbook"
    _order = "sequence asc"
    _check_company_auto = True
    _check_company_domain = models.check_company_domain_parent_of

    report_partner_id = fields.Many2one(
        "res.partner",
    )
    mail_template_id = fields.Many2one(
        "mail.template",
        "Email Template",
        domain=[("model", "=", "account.payment")],
        help="If set an email will be sent to the customer when the related account.payment.group has been posted.",
    )
    sequence = fields.Integer(help="Used to order the receiptbooks", default=10)
    name = fields.Char(
        size=64,
        required=True,
        index=True,
    )
    partner_type = fields.Selection(
        [("customer", "Customer"), ("supplier", "Vendor")],
        required=True,
        index=True,
    )
    next_number = fields.Integer(
        related="sequence_id.number_next_actual",
        readonly=False,
    )
    implementation = fields.Selection(
        related="sequence_id.implementation",
        readonly=False,
        help="Defines how the sequence assigns numbers:\n"
        "* Standard: numbers are drawn from a PostgreSQL sequence. It is fast, but the numbering "
        "may have gaps (for example if a draft payment is deleted or two payments are posted "
        "concurrently).\n"
        "* No gap: guarantees a strictly consecutive numbering, because a number is only assigned "
        "once the previous one has been assigned. Use it when the legal/fiscal numbering must not "
        "skip values. It is slower than the standard implementation: to keep numbers consecutive it "
        "locks the sequence on every assignment, so concurrent payments are serialized and have to "
        "wait for each other, which can cause noticeable delays when posting many payments at once.",
    )
    sequence_id = fields.Many2one(
        "ir.sequence",
        "Entry Sequence",
        help="This field contains the information related to the numbering of the receipt entries of this receiptbook.",
        copy=False,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    prefix = fields.Char(
        copy=False,
    )
    active = fields.Boolean(
        default=True,
    )
    document_type_id = fields.Many2one(
        "l10n_latam.document.type",
        "Document Type",
        required=True,
    )

    @api.constrains("company_id", "prefix", "document_type_id", "partner_type")
    def _check_unique_receipt(self):
        for rec in self:
            domain = [
                ("id", "!=", rec.id),
                ("company_id", "=", rec.company_id.id),
                ("prefix", "=", rec.prefix),
                ("document_type_id", "=", rec.document_type_id.id),
                ("partner_type", "=", rec.partner_type),
            ]
            if self.search(domain):
                raise UserError(
                    _(
                        "The combination of Company, Prefix, Document Type and Partner Type must be unique. "
                        "There is already a receiptbook with these values."
                    )
                )

    def write(self, vals):
        """
        If user change prefix we change prefix of sequence.
        """
        prefix = vals.get("prefix")
        for rec in self:
            if prefix and rec.sequence_id:
                rec.sequence_id.prefix = prefix
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs.ensure_sequence()
        return recs

    def ensure_sequence(self):
        """Crea el ``ir.sequence`` (padding=8, increment=1) para los
        receiptbooks de ``self`` que no lo tengan asignado. Usa el ``prefix``
        y ``company_id`` del propio receiptbook. Idempotente.
        """
        for rec in self.filtered(lambda x: not x.sequence_id):
            rec.sequence_id = (
                self.env["ir.sequence"]
                .sudo()
                .create(
                    {
                        "name": rec.name,
                        "prefix": rec.prefix,
                        "padding": 8,
                        "number_increment": 1,
                        "company_id": rec.company_id.id,
                    }
                )
            )
<<<<<<< 8be1185b7e06b1df2ccbb18a22192ee2d2920a60

    def action_resync_sequence(self):
        """Recompone ``sequence_id`` para los receiptbooks en ``self``:

        - Asegura el ``ir.sequence`` vía :meth:`ensure_sequence` (crea si falta).
        - Resuelve el último número usado vía un único ``SELECT`` que extrae
          con regex los dígitos finales del ``name`` de ``account.payment``
          (``SUBSTRING(name FROM '[0-9]+$')``) y castea ese residuo a
          ``INTEGER``, devolviendo el ``MAX``.
        - Setea ``sequence_id.number_next = max(numero) + 1`` para que el
          próximo payment posteado retome la numeración sin colisiones.

        Sirve como ejecutor de la migración 19.0.2.0.0 y como acción manual de
        reparación si la numeración se desfasa (deletes, importaciones, etc.).
        """
        self.ensure_sequence()
        self.env.flush_all()
        for rec in self:
            doc_code_prefix = rec.document_type_id.doc_code_prefix or ""
            prefix = rec.prefix or ""
            last_number = self._resync_get_last_number(rec, doc_code_prefix, prefix)
            next_number = last_number + 1
            rec.sequence_id.sudo().number_next = next_number

            _logger.info(
                "Receiptbook id=%s prefix=%r: último número=%d, ir.sequence id=%s number_next=%d",
                rec.id,
                rec.prefix,
                last_number,
                rec.sequence_id.id,
                next_number,
            )

    def _resync_get_last_number(self, rec, doc_code_prefix, prefix):
        has_main_payment = "main_payment_id" in self.env["account.payment"]._fields
        child_filter = "AND main_payment_id IS NULL" if has_main_payment else ""
        self.env.cr.execute(
            f"""
            SELECT MAX(CAST(
                SUBSTRING(
                    SPLIT_PART(REPLACE(REPLACE(name, %s, ''), %s, ''), ' ', 1)
                    FROM '[0-9]+$')
                AS INTEGER
            ))
              FROM account_payment
             WHERE receiptbook_id = %s
               AND name IS NOT NULL
               AND name LIKE %s
               {child_filter}
               AND state != 'draft'
            """,
            (
                doc_code_prefix + " ",
                prefix,
                rec.id,
                f"{doc_code_prefix} {prefix}%",
            ),
        )
        return self.env.cr.fetchone()[0] or 0
||||||| 72a9ba0ce57af6cbdd07099e3eb745b36c14b96a
        return recs
=======

    def action_resync_sequence(self):
        """Recompone ``sequence_id`` para los receiptbooks en ``self``:

        - Asegura el ``ir.sequence`` vía :meth:`ensure_sequence` (crea si falta).
        - Resuelve el último número usado vía un único ``SELECT`` que extrae
          con regex los dígitos finales del ``name`` de ``account.payment``
          (``SUBSTRING(name FROM '[0-9]+$')``) y castea ese residuo a
          ``INTEGER``, devolviendo el ``MAX``.
        - Setea ``sequence_id.number_next = max(numero) + 1`` para que el
          próximo payment posteado retome la numeración sin colisiones.

        Se usa como acción manual de reparación si la numeración se desfasa
        (deletes, importaciones, resecuenciación de recibos, etc.).
        """
        self.ensure_sequence()
        self.env.flush_all()
        for rec in self:
            doc_code_prefix = rec.document_type_id.doc_code_prefix or ""
            prefix = rec.prefix or ""
            last_number = self._resync_get_last_number(rec, doc_code_prefix, prefix)
            next_number = last_number + 1
            rec.sequence_id.sudo().number_next = next_number

            _logger.info(
                "Receiptbook id=%s prefix=%r: último número=%d, ir.sequence id=%s number_next=%d",
                rec.id,
                rec.prefix,
                last_number,
                rec.sequence_id.id,
                next_number,
            )

    def _resync_get_last_number(self, rec, doc_code_prefix, prefix):
        has_main_payment = "main_payment_id" in self.env["account.payment"]._fields
        child_filter = "AND main_payment_id IS NULL" if has_main_payment else ""
        self.env.cr.execute(
            f"""
            SELECT MAX(CAST(
                SUBSTRING(
                    SPLIT_PART(REPLACE(REPLACE(name, %s, ''), %s, ''), ' ', 1)
                    FROM '[0-9]+$')
                AS INTEGER
            ))
              FROM account_payment
             WHERE receiptbook_id = %s
               AND name IS NOT NULL
               AND name LIKE %s
               {child_filter}
               AND state != 'draft'
            """,
            (
                doc_code_prefix + " ",
                prefix,
                rec.id,
                f"{doc_code_prefix} {prefix}%",
            ),
        )
        return self.env.cr.fetchone()[0] or 0
>>>>>>> 22df653f8ced539657ef982011e42b2aaf1466be

    @api.ondelete(at_uninstall=False)
    def _unlink_except_used(self):
        # Prevent deleting used receiptbook
        is_used = self.env["account.payment"].search(
            [("receiptbook_id", "in", self.ids), ("state", "not in", ["draft", "canceled"])], limit=1
        )
        if is_used:
            raise UserError(_("You can't delete receiptbook used in publish payments."))
