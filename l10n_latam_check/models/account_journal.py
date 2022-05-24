from odoo import models, fields, api
CHECKBOOKS_BY_DEFAULT_COUNTRY_CODES = ["AR"]


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_latam_use_checkbooks = fields.Boolean(
        string='Use checkbooks?', compute="_compute_l10n_latam_use_checkbooks", store=True, readonly=False,
        inverse='_inverse_l10n_latam_use_checkbooks')
    l10n_latam_checkbook_ids = fields.One2many('l10n_latam.checkbook', 'journal_id', 'Checkbooks')

    @api.depends('outbound_payment_method_line_ids', 'company_id.country_id.code', 'check_manual_sequencing')
    def _compute_l10n_latam_use_checkbooks(self):
        arg_checks = self.filtered(
                lambda x: not x.check_manual_sequencing and x.company_id.country_id.code in CHECKBOOKS_BY_DEFAULT_COUNTRY_CODES and
                'check_printing' in x.outbound_payment_method_line_ids.mapped('code'))
        arg_checks.l10n_latam_use_checkbooks = True
        # disable checkbook if manual sequencing was enable
        self.filtered('check_manual_sequencing').l10n_latam_use_checkbooks = False

    def _inverse_l10n_latam_use_checkbooks(self):
        self.filtered('l10n_latam_use_checkbooks').check_manual_sequencing = False

    @api.onchange('l10n_latam_use_checkbooks')
    def _onchange_l10n_latam_use_checkbooks(self):
        self.filtered('l10n_latam_use_checkbooks').check_manual_sequencing = False
