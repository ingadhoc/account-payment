from odoo import models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def get_journal_dashboard_datas(self):
        # en diarios de retenciones no hacemos obligatorio default_account_id
        # pero luego la query de super da error, si no tiene este dato suponemos que es de
        # retenciones y no devolvemos nada (ademas de que la info no tendría mucho sentido)
        # chequeamos default_account_id y no los pay methods codes porque es más eficiente
        if self.type in ('bank', 'cash') and not self.default_account_id:
            return {}
        else:
            return super().get_journal_dashboard_datas()
