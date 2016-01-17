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
    'name': 'Partners Persons Management',
    'version': '8.0.1.0.1',
    'category': 'Tools',
    'sequence': 14,
    'summary': '',
    'description': """
Partners Persons Management
===========================

Openerp consider a person those partners that have not "is_company" as true, now, those partners can have:
----------------------------------------------------------------------------------------------------------

* First Name and Last Name 
* Birthdate
* Sex
* Mother and Father
* Childs
* Age (functional field)
* Nationality
* Husband/Wife
* National Identity
* Passport
* Marital Status

It also adds a configuration menu for choosing which fields do you wanna see.
    """,
    'author':  'ADHOC SA',
    'website': 'www.adhoc.com.ar',
    'license': 'AGPL-3',
    'images': [
    ],
    'depends': [
        'base',
    ],
    'data': [
        'res_partner_view.xml',
        'res_config_view.xml',
        'security/partner_person_security.xml',
    ],
    'demo': [
    ],
    'test': [
    ],
    'installable': False,
    'auto_install': False,
    'application': True,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
