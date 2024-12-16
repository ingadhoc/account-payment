# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class L10nLatamDocumentType(models.Model):

    _inherit = 'l10n_latam.document.type'

    country_id = fields.Many2one(required=False)
    internal_type = fields.Selection(
        selection_add=[('customer_payment', 'Customer Receipt'), ('supplier_payment', 'Supplier Payment')])
