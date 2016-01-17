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
    'name': 'Inter Company Move',
    'version': '8.0.1.0.1',
    'category': 'Accounting',
    'sequence': 14,
    'summary': 'Moves documents around companies in a multicompany environment,',
    'description': """
Inter Company Move
==================
    """,
    'author':  'ADHOC SA',
    'website': 'www.adhoc.com.ar',
    'license': 'AGPL-3',
    'images': [
    ],
    'depends': [
        'sale',#we add sale depency because invoice report inheritance error, it also make sense because this module is only usefull if sale is installed
        # 'l10n_ar_invoice_sale', #we add this dependency also for same error mentioned above
    ],
    'data': [
        'views/res_company_view.xml',
        'views/account_invoice_view.xml',
        'wizard/inter_company_move_wizard_view.xml',
    ],
    'demo': [
    ],
    'test': [
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: