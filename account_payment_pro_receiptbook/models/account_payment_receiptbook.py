##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL

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

    @api.depends("name", "company_id")
    @api.depends_context("allowed_company_ids")
    def _compute_display_name(self):
        """Disambiguate receiptbooks of a branch tree by suffixing the company.

        Same idea as account.tax / project.project in core: only when the user
        has more than one active company, and only if the tree actually has
        branches (otherwise the suffix is noise for single-company databases).
        """
        super()._compute_display_name()
        if len(self.env.context.get("allowed_company_ids") or []) <= 1:
            return
        for rec in self:
            # sudo: child_ids is filtered by the res.company record rule, so
            # without it the suffix would show up only for some users.
            if rec.company_id.sudo().root_id.child_ids:
                rec.display_name = f"{rec.display_name} - {rec.company_id.name}"

    @api.constrains("company_id", "prefix", "document_type_id", "partner_type")
    def _check_unique_receipt(self):
        for rec in self:
            # Uniqueness spans the whole branch tree: a branch shares the parent
            # journals, so a duplicated prefix collides on the payment move name.
            # For a company without branches root_id is itself, so child_of
            # resolves to that single company (same as the previous check).
            # sudo() to see parent/sibling receiptbooks regardless of the active
            # companies of the current user.
            domain = [
                ("id", "!=", rec.id),
                ("company_id", "child_of", rec.company_id.root_id.id),
                ("prefix", "=", rec.prefix),
                ("document_type_id", "=", rec.document_type_id.id),
                ("partner_type", "=", rec.partner_type),
            ]
            if self.sudo().search(domain):
                raise UserError(
                    _(
                        "The combination of Prefix, Document Type and Partner Type must be unique "
                        "across a company and its branches. There is already a receiptbook with these values."
                    )
                )

    @api.model
    def _get_free_prefix(self, company, document_type, partner_type):
        """Return the first free '000N-' prefix within the company branch tree
        for the given document type and partner type. Keeps '0001-' for the
        first receiptbook and bumps branches to '0002-', '0003-', ..."""
        used = set(
            self.sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("company_id", "child_of", company.root_id.id),
                    ("document_type_id", "=", document_type.id),
                    ("partner_type", "=", partner_type),
                ]
            )
            .mapped("prefix")
        )
        number = 1
        while "%04d-" % number in used:
            number += 1
        return "%04d-" % number

    @api.model
    def _resolve_branch_prefix_collisions(self):
        """Reassign a free prefix to branch receiptbooks that collide with
        another receiptbook of the same tree (same prefix/document_type/
        partner_type), keeping the one highest in the tree, then resync the
        numbering. Executor of migration 19.0.2.5.0 and manual repair action.
        """
        Company = self.env["res.company"].with_context(active_test=False)
        roots = Company.search([("parent_id", "!=", False)]).mapped("root_id")
        reassigned = self.browse()
        for root in roots:
            tree = Company.search([("id", "child_of", root.id)])
            receiptbooks = self.with_context(active_test=False).search([("company_id", "in", tree.ids)])
            # Shallow companies first so the root keeps its prefix as keeper.
            receiptbooks = receiptbooks.sorted(key=lambda r: (len((r.company_id.parent_path or "").split("/")), r.id))
            seen = set()
            for rec in receiptbooks:
                key = (rec.prefix, rec.document_type_id.id, rec.partner_type)
                if key not in seen:
                    seen.add(key)
                    continue
                new_prefix = self._get_free_prefix(rec.company_id, rec.document_type_id, rec.partner_type)
                _logger.info(
                    "Receiptbook id=%s company=%s: prefix %r -> %r (branch collision)",
                    rec.id,
                    rec.company_id.name,
                    rec.prefix,
                    new_prefix,
                )
                rec.prefix = new_prefix
                seen.add((new_prefix, rec.document_type_id.id, rec.partner_type))
                reassigned |= rec
        if reassigned:
            reassigned.action_resync_sequence()
        return reassigned

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

    def action_resync_sequence(self):
        """Recompone ``sequence_id`` para los receiptbooks en ``self``:

        - Asegura el ``ir.sequence`` vía :meth:`ensure_sequence` (crea si falta).
        - Por cada ``ir.sequence`` (varios receiptbooks pueden compartirla),
          resuelve el último número usado con el prefijo de la secuencia, que es
          el que entra en el ``name`` del pago, y no con el del receiptbook.
        - Setea ``sequence_id.number_next = max(numero) + 1`` para que el
          próximo payment posteado retome la numeración sin colisiones.

        Sirve como acción manual de reparación si la numeración se desfasa
        (deletes, importaciones, etc.).
        """
        self.ensure_sequence()
        self.env.flush_all()
        for sequence in self.mapped("sequence_id"):
            receiptbooks = self.sudo().with_context(active_test=False).search([("sequence_id", "=", sequence.id)])
            prefix = sequence._get_prefix_suffix()[0] or ""
            last_number = max(
                self._resync_get_last_number(receiptbooks, doc_code_prefix, prefix)
                for doc_code_prefix in set(receiptbooks.mapped(lambda r: r.document_type_id.doc_code_prefix or ""))
            )
            next_number = last_number + 1
            sequence.sudo().number_next = next_number

            _logger.info(
                "ir.sequence id=%s prefix=%r (receiptbooks %s): último número=%d, number_next=%d",
                sequence.id,
                prefix,
                receiptbooks.ids,
                last_number,
                next_number,
            )

    def _resync_get_last_number(self, receiptbooks, doc_code_prefix, prefix):
        # Scan by name in the whole company tree, not by receiptbook: any payment with this
        # name prefix can collide in a shared journal, even if it lost its receiptbook_id.
        has_main_payment = "main_payment_id" in self.env["account.payment"]._fields
        name_prefix = f"{doc_code_prefix} {prefix}" if doc_code_prefix else prefix
        root_ids = receiptbooks.company_id.root_id.ids
        company_ids = self.env["res.company"].sudo().search([("id", "child_of", root_ids)]).ids
        self.env.cr.execute(
            SQL(
                """
                SELECT MAX(CAST(
                    SUBSTRING(SPLIT_PART(SUBSTRING(name FROM %s), ' ', 1) FROM '^[0-9]+$')
                    AS INTEGER
                ))
                  FROM account_payment
                 WHERE company_id = ANY(%s)
                   AND name IS NOT NULL
                   AND LEFT(name, %s) = %s
                   AND state != 'draft'
                   %s
                   %s
                """,
                len(name_prefix) + 1,
                company_ids,
                len(name_prefix),
                name_prefix,
                SQL("AND main_payment_id IS NULL") if has_main_payment else SQL(),
                # Without any prefix the name alone does not identify the receiptbook.
                SQL("AND receiptbook_id = ANY(%s)", receiptbooks.ids) if not name_prefix else SQL(),
            )
        )
        return self.env.cr.fetchone()[0] or 0

    @api.ondelete(at_uninstall=False)
    def _unlink_except_used(self):
        # Prevent deleting used receiptbook
        is_used = self.env["account.payment"].search(
            [("receiptbook_id", "in", self.ids), ("state", "not in", ["draft", "canceled"])], limit=1
        )
        if is_used:
            raise UserError(_("You can't delete receiptbook used in publish payments."))
