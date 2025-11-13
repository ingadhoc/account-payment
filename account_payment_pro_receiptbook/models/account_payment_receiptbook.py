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
    last_sequence = fields.Integer(
        compute="_compute_last_sequence",
    )
    initial_sequence = fields.Integer(default=1)

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

    def _compute_last_sequence(self):
        for rec in self:
            move_id = self.env["account.move"].search(
                [("receiptbook_id", "=", rec.id), ("name", "!=", "/")], order="sequence_number DESC", limit=1
            )
            rec.last_sequence = move_id.sequence_number

    @api.ondelete(at_uninstall=False)
    def _unlink_except_used(self):
        # Prevent deleting used receiptbook
        is_used = self.env["account.payment"].search(
            [("receiptbook_id", "in", self.ids), ("state", "not in", ["draft", "canceled"])], limit=1
        )
        if is_used:
            raise UserError(_("You can't delete receiptbook used in publish payments."))
