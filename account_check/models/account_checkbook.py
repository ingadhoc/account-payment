# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import fields, models, api, _
import logging
from openerp.exceptions import ValidationError
_logger = logging.getLogger(__name__)


class AccountCheckbook(models.Model):

    _name = 'account.checkbook'
    _description = 'Account Checkbook'

    name = fields.Char(
        compute='_compute_name',
    )
    sequence_id = fields.Many2one(
        'ir.sequence',
        'Sequence',
        copy=False,
        domain=[('code', '=', 'issue_check')],
        help="Checks numbering sequence.",
        context={'default_code': 'issue_check'},
        # sacamos lo de states ya que molesta más que ayudar
        # readonly=True,
        # states={'draft': [('readonly', False)]},
    )
    next_number = fields.Integer(
        'Next Number',
        compute='_compute_next_number',
        inverse='_inverse_next_number',
        # usamos compute para poder usar sudo cuando se setea secuencia sin
        # necesidad de dar permiso en ir.sequence
        # related='sequence_id.number_next_actual',
    )
    issue_check_subtype = fields.Selection(
        [('deferred', 'Deferred'), ('currents', 'Currents')],
        string='Issue Check Subtype',
        required=True,
        default='deferred',
        help='* Con cheques corrientes el asiento generado por el pago '
        'descontará directamente de la cuenta de banco y además la fecha de '
        'pago no es obligatoria.\n'
        '* Con cheques diferidos el asiento generado por el pago se hará '
        'contra la cuenta definida para tal fin en la compañía, luego será '
        'necesario el asiento de débito que se puede generar desde el extracto'
        ' o desde el cheque.',
        # readonly=True,
        # states={'draft': [('readonly', False)]}
    )
    journal_id = fields.Many2one(
        'account.journal', 'Journal',
        help='Journal where it is going to be used',
        readonly=True,
        required=True,
        domain=[('type', '=', 'bank')],
        ondelete='cascade',
        context={'default_type': 'bank'},
        states={'draft': [('readonly', False)]}
    )
    range_to = fields.Integer(
        'To Number',
        # readonly=True,
        # states={'draft': [('readonly', False)]},
        help='If you set a number here, this checkbook will be automatically'
        ' set as used when this number is raised.'
    )
    issue_check_ids = fields.One2many(
        'account.check',
        'checkbook_id',
        string='Issue Checks',
        readonly=True,
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('active', 'In Use'), ('used', 'Used')],
        string='State',
        # readonly=True,
        default='draft',
        copy=False
    )
    # TODO depreciar esta funcionalidad que no estamos usando
    block_manual_number = fields.Boolean(
        default=True,
        string='Block manual number?',
        # readonly=True,
        # states={'draft': [('readonly', False)]},
        help='Block user to enter manually another number than the suggested'
    )
    numerate_on_printing = fields.Boolean(
        default=False,
        string='Numerate on printing?',
        # readonly=True,
        # states={'draft': [('readonly', False)]},
        help='No number will be assigne while creating payment, number will be'
        'assigned after printing check.'
    )
    report_template = fields.Many2one(
        'ir.actions.report.xml',
        'Report',
        domain="[('model', '=', 'account.payment')]",
        context="{'default_model': 'account.payment'}",
        help='Report to use when printing checks. If not report selected, '
        'report with name "check_report" will be used')

    @api.multi
    @api.depends('sequence_id.number_next_actual')
    def _compute_next_number(self):
        for rec in self:
            rec.next_number = rec.sequence_id.number_next_actual

    @api.multi
    def _inverse_next_number(self):
        for rec in self.filtered('sequence_id'):
            rec.sequence_id.sudo().number_next_actual = rec.next_number

    @api.model
    def create(self, vals):
        rec = super(AccountCheckbook, self).create(vals)
        if not rec.sequence_id:
            rec._create_sequence()
        return rec

    @api.one
    def _create_sequence(self):
        """ Create a check sequence for the checkbook """
        self.sequence_id = self.env['ir.sequence'].sudo().create({
            'name': '%s - %s' % (self.journal_id.name, self.name),
            'implementation': 'no_gap',
            'padding': 8,
            'number_increment': 1,
            'code': 'issue_check',
            # si no lo pasamos, en la creacion se setea 1
            'number_next_actual': self.next_number,
            'company_id': self.journal_id.company_id.id,
        })

    @api.multi
    def _compute_name(self):
        for rec in self:
            if rec.issue_check_subtype == 'deferred':
                name = _('Deferred Checks')
            else:
                name = _('Currents Checks')
            if rec.range_to:
                name += _(' up to %s') % rec.range_to
            rec.name = name

    @api.one
    def unlink(self):
        if self.issue_check_ids:
            raise ValidationError(
                _('You can drop a checkbook if it has been used on checks!'))
        return super(AccountCheckbook, self).unlink()
