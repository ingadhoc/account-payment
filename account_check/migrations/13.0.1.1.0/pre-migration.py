# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging
_logger = logging.getLogger(__name__)

def create_column_table(cr):
    _logger.info('AAAA')


def migrate(cr, version):
    create_column_table(cr)
