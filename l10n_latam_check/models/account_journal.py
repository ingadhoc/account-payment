from odoo import models, fields, api


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_latam_use_checkbooks = fields.Boolean(
        string='Use checkbooks?', compute="_compute_l10n_latam_use_checkbooks", store=True, readonly=False,
        inverse='_inverse_l10n_latam_use_checkbooks', copy=False)
    l10n_latam_checkbook_ids = fields.One2many('l10n_latam.checkbook', 'journal_id', 'Checkbooks')

    @api.model
    def _get_checkbooks_by_default_country_codes(self):
        """ Return the list of country codes for the countries where using checkbooks is enable by default """
        return ["AR"]

    @api.depends('outbound_payment_method_line_ids', 'company_id.country_id.code', 'check_manual_sequencing')
    def _compute_l10n_latam_use_checkbooks(self):
        arg_checks = self.filtered(
                lambda x: not x.check_manual_sequencing and x.company_id.country_id.code in self._get_checkbooks_by_default_country_codes() and
                'check_printing' in x.outbound_payment_method_line_ids.mapped('code'))
        arg_checks.l10n_latam_use_checkbooks = True
        # disable checkbook if manual sequencing was enable
        self.filtered('check_manual_sequencing').l10n_latam_use_checkbooks = False

    @api.onchange('l10n_latam_use_checkbooks')
    def _inverse_l10n_latam_use_checkbooks(self):
        self.filtered('l10n_latam_use_checkbooks').check_manual_sequencing = False
