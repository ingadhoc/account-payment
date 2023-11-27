from odoo import api, fields, models, tools, _
import logging

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _loader_params_account_card_installment(self):
        result = super()._loader_params_account_card_installment()
        result['search_params']['fields'].append('financial_surcharge')
        return result

    def _loader_params_pos_payment_method(self):
        params = super(PosSession, self)._loader_params_pos_payment_method()
        params['search_params']['domain'] = [('card_id', '!=', False)]
        params['search_params']['fields'].append('card_id')
        params['search_params']['fields'].append('instalment_ids')
        params['search_params']['fields'].append('instalment_product_id')
        return params

    def _pos_ui_models_to_load(self):
        result = super()._pos_ui_models_to_load()
        new_model = 'account.card.installment'
        if new_model not in result:
            result.append(new_model)
        return result

    def _loader_params_account_card_installment(self):
        return {
            'search_params': {
                'domain': [('card_id', '!=', False)],
                'fields': [
                    'card_id', 'name', 'installment', 'divisor', 'surcharge_coefficient', 'bank_discount', 'active', 'financial_surcharge'
                ],
            }
        }

    def _get_pos_ui_account_card_installment(self, custom_search_params):
        params = self._loader_params_account_card_installment()
        params['search_params'] = {**params['search_params'], **custom_search_params}
        payment = self.env['account.card.installment'].search_read(**custom_search_params['search_params'])
        return payment




