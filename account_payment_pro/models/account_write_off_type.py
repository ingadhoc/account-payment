from odoo import api, fields, models


class AccountWrite_offType(models.Model):
    _name = "account.write_off.type"
    _description = "account.write_off.type"
    _check_company_domain = models.check_companies_domain_parent_of

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    label = fields.Char(help="Label to be used on journal items labels, if not configured name will be used")
    account_id = fields.Many2one(
        "account.account",
        required=True,
        domain="[('deprecated', '=', False), ('account_type', 'in', ['expense', 'income', 'income_other'])]",
    )
    company_ids = fields.Many2many("res.company", string="Companies", store=True, compute="_compute_company_ids")
    # NTH implementar tolerance para que se pueda restringir importe (en valor porcentual? absoluto?)
    # tolerance = fields.Floar()

    @api.depends("account_id")
    def _compute_company_ids(self):
        for rec in self:
            rec.company_ids = rec.account_id.company_ids
