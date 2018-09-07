##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields


class AccountPaymentReceiptbook(models.Model):

    _inherit = "account.payment.receiptbook"

    mail_template_id = fields.Many2one(
        'mail.template',
        'Email Template',
        domain=[('model', '=', 'account.payment.group')],
        help="If set an email will be sent to the customer when the related"
        " account.payment.group has been posted.",
    )
