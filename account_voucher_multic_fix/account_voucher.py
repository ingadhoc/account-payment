# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, api, fields, _


class account_voucher(models.Model):

    _inherit = "account.voucher"

    available_journal_ids = fields.Many2many(
        'account.journal',
        compute='_get_available_journals',
        string=_('Available Journals'),
        )

    @api.one
    @api.depends('company_id')
    def _get_available_journals(self):
        self.available_journal_ids = self.env['account.journal']
        journal_ids = []
        if self.company_id:
            domain = [
                ('company_id', '=', self.company_id.id),
                ('type', 'in', ('cash', 'bank'))]
            # Esto seria si esta instalado el modulo de direction
            if self.env['account.journal'].fields_get(['direction']):
                if self._context.get('type', False) == 'payment':
                    domain.append(('direction', 'in', [False, 'out']))
                elif self._context.get('type', False) == 'receipt':
                    domain.append(('direction', 'in', [False, 'in']))
            journal_ids = self.env['account.journal'].search(domain)
        self.available_journal_ids = journal_ids

    @api.onchange('company_id')
    def on_change_company_new_api(self):
        """El onchange por defecto de account voucher esta presente en algunas
        vistas y otras no, por eso lo borramos de la que nos interesa y lo
        hacemos con la nueva api. El onchange original no hacia mucho que
        digamos
        """
        self.journal_id = False
        # TODO borrar esto que ya no seria necesario
        # Better to not return any journal, this helps in an error of account
        # not configured on payment dialog, also it force user to select right
        # journal and not make mistaes
        # self.journal_id = (
        #     self.available_journal_ids and self.available_journal_ids[0].id
        #     or False)

        # TODO antes era necesiaro cambiar el periodo pero parece que ahora no
        # por las dudas dejamos algo de codigo que deberia ayudar en tal caso
        # result = self.onchange_date(
        #     cr, uid, ids, date, currency_id, payment_rate_currency_id,
        #     amount, company_id, context=context)
        # y de result tenemos que tomar period

    @api.multi
    def recompute_voucher_lines(
            self, partner_id, journal_id, price, currency_id,
            ttype, date):
        '''Modification of this method so that only the moves of selected
        journal company are considered.
        We select the move lines and send them in the context'''
        move_lines = self.get_move_lines(ttype, partner_id, journal_id)
        # if not move lines we dont want recompute voucher to compute them,
        # we leave them empty
        if not move_lines:
            return {
                'value': {
                    'line_dr_ids': [], 'line_cr_ids': [], 'pre_line': False},
            }
        return super(account_voucher, self.with_context(
                move_line_ids=move_lines.ids)).recompute_voucher_lines(
                    partner_id, journal_id, price, currency_id, ttype,
                    date)

    @api.model
    def get_move_lines(self, ttype, partner_id, journal_id):
        # we not only fix that move lines should be from journal company
        # but also we make right search when sellecting contacts of companies
        company = self.env['account.journal'].browse(journal_id).company_id
        # we would like to search by commercial but later, when creating
        # the move, it would give an error with differetns partners.
        # perhups we can move all this to voucher_payline
        # commercial_partner = self.env['res.partner'].browse(
        #     partner_id).commercial_partner_id

        if self._context.get('move_line_ids'):
            domain = [
                ('id', 'in', self._context.get('move_line_ids')),
                ('company_id', '=', company.id),
            ]
        else:
            account_type = None
            if self._context.get('account_id'):
                account_type = self.env['account.account'].browse(
                    self._context['account_id']).type
            if ttype == 'payment':
                if not account_type:
                    account_type = 'payable'
            else:
                if not account_type:
                    account_type = 'receivable'
            domain = [
                ('state', '=', 'valid'),
                ('company_id', '=', company.id),
                ('account_id.type', '=', account_type),
                ('reconcile_id', '=', False),
                ('partner_id', '=', partner_id)]
        move_lines = self.env['account.move.line'].search(domain)
        return move_lines
