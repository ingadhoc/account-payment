# © 2024 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, _
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):

    _inherit = "account.journal"

    def _get_manual_payment_method_id(self, direction='inbound'):
        self.ensure_one()
        if direction == 'inbound':
            payment_method = self.inbound_payment_method_line_ids.payment_method_id.filtered(lambda x: x.code == 'manual')
        else:
            payment_method = self.outbound_payment_method_line_ids.payment_method_id.filtered(lambda x: x.code == 'manual')
        if not payment_method:
            raise ValidationError(_('Journal must have manual method!'))
        return payment_method
