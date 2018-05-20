# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
from openerp import api, SUPERUSER_ID
_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    """
    Add document number from payments on install
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    payments = env['account.payment'].search(
        [('payment_type', '!=', 'transfer')])
    # TODO improove this because it is too slow, perhups because of name
    # computation
    for payment in payments:
        payment.payment_group_id.write({
            'document_number': payment.document_number,
            'receiptbook_id': payment.receiptbook_id.id,
        })
