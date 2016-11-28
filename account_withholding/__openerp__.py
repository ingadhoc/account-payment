# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015  ADHOC SA  (http://www.adhoc.com.ar)
#    All Rights Reserved.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
{
    'author': 'ADHOC SA',
    'website': 'www.adhoc.com.ar',
    'license': 'AGPL-3',
    'category': 'Accounting & Finance',
    'data': [
        'views/account_tax_view.xml',
        'views/account_payment_view.xml',
        'data/account_payment_method_data.xml',
        # TODO delete or enable, we should create it on chart installation
        # if we create it from here accounts will be created, so we let
        # this work to chart installation
        # 'data/account_journal_data.xml',
    ],
    'depends': [
        'account',
    ],
    'installable': True,
    'name': 'Withholdings on Payments',
    'test': [],
    'version': '9.0.1.0.0',
}
