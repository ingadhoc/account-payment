from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    l10n_latam_check_numbers = fields.Char(string="Check Numbers", compute="_compute_l10n_latam_check_numbers")

    @api.depends("l10n_latam_new_check_ids.name", "l10n_latam_move_check_ids.name")
    def _compute_l10n_latam_check_numbers(self):
        for rec in self:
            checks = rec.l10n_latam_new_check_ids | rec.l10n_latam_move_check_ids
            rec.l10n_latam_check_numbers = ", ".join(checks.filtered("name").mapped("name"))
