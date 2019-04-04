##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, api


class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    @api.multi
    def send_mail(self, auto_commit=False):
        context = self._context
        if context.get('default_model') == 'account.payment.group' and \
                context.get('default_res_id') and context.get(
                    'mark_payment_as_sent'):
            payment = self.env['account.payment.group'].browse(
                context['default_res_id'])
            if not payment.sent:
                payment.sent = True
            self = self.with_context(
                mail_post_autofollow=True, lang=payment.partner_id.lang)
        return super(MailComposeMessage, self).send_mail(
            auto_commit=auto_commit)
