from odoo import fields, models, _, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_date
from odoo.osv import expression
import logging
_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):

    _inherit = 'account.payment'

    # Third party check operation links
    l10n_latam_check_id = fields.Many2one(
        'account.payment', string='Check', readonly=True,
        states={'draft': [('readonly', False)]}, copy=False)
    l10n_latam_check_operation_ids = fields.One2many(
        'account.payment', 'l10n_latam_check_id', readonly=True, string='Check Operations')
    l10n_latam_check_current_journal_id = fields.Many2one(
        'account.journal', compute='_compute_l10n_latam_check_current_journal',
        string="Check Current Journal", store=True)
    # Warning message in case of unlogical third party check operations
    l10n_latam_check_warning_msg = fields.Html(compute='_compute_l10n_latam_check_warning_msg')

    # Check number override as we want to set it manually
    check_number = fields.Char(readonly=False)

    # New third party check info
    l10n_latam_check_bank_id = fields.Many2one(
        'res.bank', readonly=True, states={'draft': [('readonly', False)]},
        compute='_compute_l10n_latam_check_data', store=True, string='Check Bank')
    l10n_latam_check_issuer_vat = fields.Char(
        readonly=True, states={'draft': [('readonly', False)]},
        compute='_compute_l10n_latam_check_data', store=True, string='Check Issuer VAT')
    l10n_latam_check_payment_date = fields.Date(
        string='Check Payment Date', readonly=True, states={'draft': [('readonly', False)]})

    # Check book
    l10n_latam_use_checkbooks = fields.Boolean(related='journal_id.l10n_latam_use_checkbooks')
    l10n_latam_checkbook_type = fields.Selection(related='l10n_latam_checkbook_id.type')
    l10n_latam_checkbook_id = fields.Many2one(
        'l10n_latam.checkbook', 'Checkbook', store=True,
        compute='_compute_l10n_latam_checkbook', readonly=True, states={'draft': [('readonly', False)]})

    @api.depends('payment_method_line_id.code', 'journal_id.l10n_latam_use_checkbooks')
    def _compute_l10n_latam_checkbook(self):
        with_checkbooks = self.filtered(lambda x: x.payment_method_line_id.code == 'check_printing' and
                                                  x.journal_id.l10n_latam_use_checkbooks)
        (self - with_checkbooks).l10n_latam_checkbook_id = False
        for rec in with_checkbooks:
            checkbooks = rec.journal_id.l10n_latam_checkbook_ids
            if rec.l10n_latam_checkbook_id and rec.l10n_latam_checkbook_id in checkbooks:
                continue
            rec.l10n_latam_checkbook_id = checkbooks and checkbooks[0] or False

    @api.depends('l10n_latam_checkbook_id', 'journal_id', 'payment_method_code')
    def _compute_check_number(self):
        """ Override from account_check_printing"""
        from_checkbooks = self.filtered(lambda x: x.l10n_latam_checkbook_id)
        for pay in from_checkbooks:
            # we don't recompute when creating from a method and if check_number is sent
            if pay.check_number and not isinstance(pay.id, models.NewId):
                continue
            pay.check_number = pay.l10n_latam_checkbook_id.sequence_id.get_next_char(
                pay.l10n_latam_checkbook_id.next_number)
        return super(AccountPayment, self - from_checkbooks)._compute_check_number()

    def _inverse_check_number(self):
        """ On third party checks or own checks with checkbooks, avoid calling super because is not needed to write the
        sequence for these use case. """
        avoid_inverse = self.filtered(
            lambda x: x.l10n_latam_checkbook_id or x.payment_method_line_id.code == 'new_third_party_checks')
        return super(AccountPayment, self - avoid_inverse)._inverse_check_number()

    @api.constrains('check_number', 'journal_id', 'state')
    def _constrains_check_number(self):
        """ Don't enforce uniqueness for third party checks"""
        third_party_checks = self.filtered(lambda x: x.payment_method_line_id.code == 'new_third_party_checks')
        return super(AccountPayment, self - third_party_checks)._constrains_check_number()

    def action_unmark_sent(self):
        """ Unmarking as sent for check with checkbooks would give the option to print and re-number check but
        it's not implemented yet for this kind of checks"""
        if self.filtered('l10n_latam_checkbook_id'):
            raise UserError(_('Unmark sent is not implemented for checks that use checkbooks'))
        return super().action_unmark_sent()

    @api.onchange('l10n_latam_check_id')
    def _onchange_check(self):
        for rec in self.filtered('l10n_latam_check_id'):
            rec.amount = rec.l10n_latam_check_id.amount

    @api.depends('payment_method_line_id.code', 'partner_id')
    def _compute_l10n_latam_check_data(self):
        new_third_party_checks = self.filtered(lambda x: x.payment_method_line_id.code == 'new_third_party_checks')
        for rec in new_third_party_checks:
            rec.update({
                'l10n_latam_check_bank_id': rec.partner_id.bank_ids and rec.partner_id.bank_ids[0].bank_id or False,
                'l10n_latam_check_issuer_vat': rec.partner_id.vat,
            })

    @api.depends(
        'payment_method_line_id', 'l10n_latam_check_issuer_vat', 'l10n_latam_check_bank_id', 'company_id',
        'check_number', 'l10n_latam_check_id', 'state', 'date', 'is_internal_transfer')
    def _compute_l10n_latam_check_warning_msg(self):
        self.l10n_latam_check_warning_msg = False
        for rec in self.filtered(lambda x: x.state == 'draft'):
            if rec.l10n_latam_check_id:
                date = rec.date or fields.Datetime.now()
                last_operation = rec.env['account.payment'].search([
                    ('state', '=', 'posted'), '|', ('l10n_latam_check_id', '=', rec.l10n_latam_check_id.id),
                    ('id', '=', rec.l10n_latam_check_id.id)], order="date desc, id desc", limit=1)
                if last_operation and last_operation[0].date > date:
                    rec.l10n_latam_check_warning_msg = _(
                        "It seems you're trying to move a check with a date (%s) prior to last operation done with "
                        "the check (%s). This may be wrong, please double check it. If continue, last operation on "
                        "the check will remain being %s") % (
                            format_date(self.env, date), last_operation.display_name, last_operation.display_name)
                elif not rec.is_internal_transfer and rec.payment_type == 'inbound' and rec.partner_type != last_operation.partner_type:
                    rec.l10n_latam_check_warning_msg = _(
                        "It seems you're receiving back a check from '%s' with a different payment type than "
                        "when sending it. It is advisable to use the same payment type (customer payment / supplier "
                        "payment) so that the same receivable / payable account is used") % (rec.partner_id.name)

            elif rec.check_number and rec.payment_method_line_id.code == 'new_third_party_checks' and \
                    rec.l10n_latam_check_bank_id and rec.l10n_latam_check_issuer_vat:
                same_checks = self.search([
                    ('company_id', '=', rec.company_id.id),
                    ('l10n_latam_check_bank_id', '=', rec.l10n_latam_check_bank_id.id),
                    ('l10n_latam_check_issuer_vat', '=', rec.l10n_latam_check_issuer_vat),
                    ('check_number', '=', rec.check_number),
                    ('id', '!=', rec._origin.id)])
                if same_checks:
                    rec.l10n_latam_check_warning_msg = _(
                        "Other checks were found with same number, issuer and bank. Please double check you are not "
                        "encoding the same check more than once<br/>"
                        "List of other payments/checks: %s") % (",".join(same_checks.mapped('display_name')))
            elif rec.l10n_latam_checkbook_id.range_to and rec.check_number.isdecimal() and int(rec.check_number) > rec.l10n_latam_checkbook_id.range_to:
                rec.l10n_latam_check_warning_msg = _(
                        "The <strong>check number %s is bigger</strong> than max number for this checkbook.<br/>"
                        "Please check you're using the right check number and the right checkbook") % (rec.check_number)

    def _get_payment_method_codes_to_exclude(self):
        res = super(AccountPayment, self)._get_payment_method_codes_to_exclude()
        if self.is_internal_transfer:
            res.append('new_third_party_checks')
        return res

    @api.depends('is_internal_transfer')
    def _compute_payment_method_line_fields(self):
        """ Add is_internal_transfer as a trigger to re-compute """
        return super()._compute_payment_method_line_fields()

    def action_post(self):
        # third party checks validations
        for rec in self:
            if rec.l10n_latam_check_id and not rec.currency_id.is_zero(rec.l10n_latam_check_id.amount - rec.amount):
                raise UserError(_(
                    'The amount of the payment (%s) does not match the amount of the selected check (%s).\n'
                    'Please try to deselect and select check again.') % (rec.amount, rec.l10n_latam_check_id.amount))
            elif rec.payment_method_line_id.code in ['in_third_party_checks', 'out_third_party_checks']:
                if rec.l10n_latam_check_id.state != 'posted':
                    raise ValidationError(_('Selected check "%s" is not posted') % rec.l10n_latam_check_id.display_name)
                elif (
                        rec.payment_type == 'outbound' and
                        rec.l10n_latam_check_id.l10n_latam_check_current_journal_id != rec.journal_id) or (
                        rec.payment_type == 'inbound' and rec.is_internal_transfer and
                        rec.l10n_latam_check_id.l10n_latam_check_current_journal_id != rec.destination_journal_id):
                    # check outbound payment and transfer or inbound transfer
                    raise ValidationError(_(
                        'Check "%s" is not anymore in journal "%s", it seems it has been moved by another payment.') % (
                            rec.l10n_latam_check_id.display_name, rec.journal_id.name
                            if rec.payment_type == 'outbound' else rec.destination_journal_id.name))
                elif rec.payment_type == 'inbound' and not rec.is_internal_transfer and \
                        rec.l10n_latam_check_id.l10n_latam_check_current_journal_id:
                    raise ValidationError(_("Check '%s' is on journal '%s', we can't receive it again") % (
                        rec.l10n_latam_check_id.display_name, rec.journal_id.name))

        res = super().action_post()

        # mark own checks that are not printed as sent
        for rec in self.filtered('l10n_latam_checkbook_id'):
            sequence = rec.l10n_latam_checkbook_id.sequence_id
            sequence.sudo().write({'number_next_actual': int(rec.check_number) + 1})
            rec.write({'is_move_sent': True})
        return res

    @api.onchange('payment_method_line_id', 'is_internal_transfer', 'journal_id', 'destination_journal_id')
    def reset_check_ids(self):
        """ If any of this fields changes the domain of the selectable checks could change """
        self.l10n_latam_check_id = False

    @api.onchange('check_number')
    def _onchange_check_number(self):
        for rec in self.filtered(
                lambda x: x.journal_id.company_id.country_id.code == "AR" and x.check_number and x.check_number.isdecimal()):
            rec.check_number = '%08d' % int(rec.check_number)

    @api.depends('l10n_latam_check_operation_ids.state')
    def _compute_l10n_latam_check_current_journal(self):
        new_checks = self.filtered(lambda x: x.payment_method_line_id.code == 'new_third_party_checks')
        payments = self.env['account.payment'].search(
            [('l10n_latam_check_id', 'in', new_checks.ids), ('state', '=', 'posted')], order="date desc, id desc")

        # we store on a dict the first payment (last operation) for each check
        checks_mapping = {}
        for payment in payments:
            if payment.l10n_latam_check_id not in checks_mapping:
                checks_mapping[payment.l10n_latam_check_id] = payment

        for rec in new_checks:
            last_operation = checks_mapping.get(rec)
            if not last_operation:
                rec.l10n_latam_check_current_journal_id = rec.journal_id
                continue
            if last_operation.is_internal_transfer and last_operation.payment_type == 'outbound':
                rec.l10n_latam_check_current_journal_id = last_operation.paired_internal_transfer_payment_id.journal_id
            elif last_operation.payment_type == 'inbound':
                rec.l10n_latam_check_current_journal_id = last_operation.journal_id
            else:
                rec.l10n_latam_check_current_journal_id = False

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        res = super()._get_trigger_fields_to_synchronize()
        return res + ('check_number',)

    def _prepare_move_line_default_vals(self, write_off_line_vals=None):
        """ Add check name and operation on liquidity line """
        res = super()._prepare_move_line_default_vals(write_off_line_vals=write_off_line_vals)
        check = self if (self.payment_method_line_id.code == 'new_third_party_checks' or self.l10n_latam_checkbook_id) \
            else self.l10n_latam_check_id
        if check:
            document_name = (_('Check %s received') if self.payment_type == 'inbound' else _('Check %s delivered')) % (
                check.check_number)
            res[0].update({
                'name': self.env['account.move.line']._get_default_line_name(
                    document_name, self.amount, self.currency_id, self.date, partner=self.partner_id),
            })
            res[0].update({})
        return res

    def name_get(self):
        """ Add check number to display_name on check_id m2o field """
        res_names = super().name_get()
        for i, (res_name, rec) in enumerate(zip(res_names, self)):
            if rec.check_number and rec.payment_method_line_id.code == 'new_third_party_checks':
                res_names[i] = (res_name[0], "%s %s" % (res_name[1], _("(Check %s)", rec.check_number)))
        return res_names

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        """ Allow to search by check_number """
        args = args or []
        if operator == 'ilike' and not (name or '').strip():
            domain = []
        else:
            connector = '&' if operator in expression.NEGATIVE_TERM_OPERATORS else '|'
            domain = [connector, ('check_number', operator, name), ('name', operator, name)]
        return self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid)

    def button_open_check_operations(self):
        ''' Redirect the user to the invoice(s) paid by this payment.
        :return:    An action on account.move.
        '''
        self.ensure_one()

        operations = (self.l10n_latam_check_operation_ids.filtered(lambda x: x.state == 'posted') + self)
        action = {
            'name': _("Check Operations"),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'views': [
                (self.env.ref('l10n_latam_check.view_account_third_party_check_operations_tree').id, 'tree'),
                (False, 'form')],
            'context': {'create': False},
            'domain': [('id', 'in', operations.ids)],
        }
        return action

    def _create_paired_internal_transfer_payment(self):
        """
        Two modifications when only when transferring from a third party checks journal:
        1. When a paired transfer is created, the default odoo behavior is to use on the paired transfer the first
        available payment method. If we are transferring to another third party checks journal, then set as payment method
        on the paired transfer 'in_third_party_checks' or 'out_third_party_checks'
        2. On the paired transfer set the l10n_latam_check_id field, this field is needed for the
        l10n_latam_check_operation_ids and also for some warnings and constrains.
        """
        for rec in self.filtered(lambda x: x.payment_method_line_id.code in ['in_third_party_checks', 'out_third_party_checks']):
            dest_payment_method_code = 'in_third_party_checks' if rec.payment_type == 'outbound' else 'out_third_party_checks'
            dest_payment_method = rec.destination_journal_id.inbound_payment_method_line_ids.filtered(
                lambda x: x.code == dest_payment_method_code)
            if dest_payment_method:
                super(AccountPayment, rec.with_context(
                    default_payment_method_line_id=dest_payment_method.id,
                    default_l10n_latam_check_id=rec.l10n_latam_check_id))._create_paired_internal_transfer_payment()
            else:
                super(AccountPayment, rec.with_context(
                    default_l10n_latam_check_id=rec.l10n_latam_check_id))._create_paired_internal_transfer_payment()
            self -= rec
        super(AccountPayment, self)._create_paired_internal_transfer_payment()
