# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_financial_charge = fields.Boolean(string="Recargo financiero?")
