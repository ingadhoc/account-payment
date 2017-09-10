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
        readonly=True,
        copy=False,
        domain=[('code', '=', 'issue_check')],
        help="Checks numbering sequence.",
        context={'default_code': 'issue_check'},
        states={'draft': [('readonly', False)]},
    )
    next_number = fields.Integer(
        'Next Number',
        related='sequence_id.number_next_actual',
    )
    issue_check_subtype = fields.Selection(
        [('deferred', 'Deferred'), ('currents', 'Currents')],
        string='Issue Check Subtype',
        readonly=True,
        required=True,
        default='deferred',
        help=u'* Con cheques corrientes el asiento generado por el pago '
        u'descontará directamente de la cuenta de banco y además la fecha de '
        u'pago no es obligatoria.\n'
        u'* Con cheques diferidos el asiento generado por el pago se hará '
        u'contra la cuenta definida para tal fin en la compañía, luego será '
        u'necesario el asiento de débito que se puede generar desde el '
        u'extracto o desde el cheque.',
        states={'draft': [('readonly', False)]}
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
        readonly=True,
        states={'draft': [('readonly', False)]},
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
    block_manual_number = fields.Boolean(
        readonly=True,
        default=True,
        string='Block manual number?',
        states={'draft': [('readonly', False)]},
        help='Block user to enter manually another number than the suggested'
    )

    @api.model
    def create(self, vals):
        rec = super(AccountCheckbook, self).create(vals)
        if not rec.sequence_id:
            rec._create_sequence()
        return rec

    @api.multi
    def _create_sequence(self):
        """ Create a check sequence for the checkbook """
        for rec in self:
            rec.sequence_id = rec.env['ir.sequence'].sudo().create({
                'name': '%s - %s' % (rec.journal_id.name, rec.name),
                'implementation': 'no_gap',
                'padding': 8,
                'number_increment': 1,
                'code': 'issue_check',
                'company_id': rec.journal_id.company_id.id,
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

    @api.multi
    def unlink(self):
        if self.mapped('issue_check_ids'):
            raise ValidationError(
                _('You can drop a checkbook if it has been used on checks!'))
        return super(AccountCheckbook, self).unlink()
