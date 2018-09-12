from odoo import api, models


class AccountMoveLine(models.Model):

    _inherit = 'account.move.line'

    @api.model
    def create(self, values):
        """ Fix the account.move.line account when this one is create as a new
        aml from reconcilation wizard
        """
        new_aml_dicts = self._context.get('new_aml_dicts', False)
        if new_aml_dicts and values in new_aml_dicts:
            self.fix_widget_account(values)

        return super(AccountMoveLine, self).create(values)

    @api.model
    def fix_widget_account(self, values):
        """ Corregir la cuenta a usar, si estoy validando una linea sola.

        Si soy proveedor usar cuenta de proveedores del partner (pagable).
        Si soy partner cliente usar cuenta deudora por venta (a cobrar)
        """
        partner_obj = self.env['res.partner']
        fix_account_id = False
        partner = partner_obj.browse(values.get('partner_id', False))
        if partner.supplier and partner.customer:
            pass
        elif partner.supplier:
            fix_account_id = partner.property_account_payable_id.id
        elif partner.customer:
            fix_account_id = partner.property_account_receivable_id.id

        if fix_account_id:
            values.update({'account_id': fix_account_id})
