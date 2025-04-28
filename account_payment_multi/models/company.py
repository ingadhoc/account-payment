from odoo import fields, models, _


class ResCompany(models.Model):
    _inherit = "res.company"

    batch_payment_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        readonly=True,
        copy=False,
        default=lambda self: self.env['ir.sequence'].sudo().create({
            'name': _("Batch Payment Number Sequence"),
            'implementation': 'no_gap',
            'padding': 5,
            'use_date_range': True,
            'company_id': self.id,
            'prefix': 'BATCH/%(year)s/',
        }),
    )

    def get_next_batch_payment_communication(self):
        '''
        When in need of a batch payment communication reference (several invoices paid at the same time)
        use batch_payment_sequence_id to get it (eventually create it first): e.g BATCH/2024/00001
        '''
        self.ensure_one()
        return self.sudo().batch_payment_sequence_id.next_by_id()
