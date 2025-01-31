from odoo import models, fields


class AccountWrite_offType(models.Model):
    _name = 'account.write_off.type'
    _description = 'account.write_off.type'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    label = fields.Char(help='Label to be used on journal items labels, if not configured name will be used')
    account_id = fields.Many2one(
        'account.account', required=True,
        domain="[('deprecated', '=', False), ('account_type', 'in', ['expense', 'income', 'income_other'])]",
    )
    company_id = fields.Many2one(related='account_id.company_id', store=True,)
    # NTH implementar tolerance para que se pueda restringir importe (en valor porcentual? absoluto?)
    # tolerance = fields.Floar()
