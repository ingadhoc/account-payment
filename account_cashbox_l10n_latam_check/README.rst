.. |company| replace:: ADHOC SA

.. |company_logo| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-logo.png
   :alt: ADHOC SA
   :target: https://www.adhoc.com.ar

.. |icon| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-icon.png

.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

================================
Account Cashbox l10n Latam Check
================================

This module integrates the Latin American check management system with cashbox sessions, providing seamless check transfer operations within point-of-sale (POP) sessions.

**Main Features:**
- Integrates third-party check operations with cashbox session management
- Adds cashbox session selection to mass check transfer wizard
- Enforces cashbox session requirement for users when configured
- Automatically links check payments to active cashbox sessions

Installation
============

This module has the following dependencies:

* ``account_cashbox`` - For cashbox session management
* ``l10n_latam_check`` - For Latin American check handling

The module is configured as ``auto_install=True``, meaning it will be automatically installed when both dependencies are present.

Configuration
=============

**User Configuration:**

#. Go to **Settings > Users & Companies > Users**
#. Select a user and check the field "Requires Account Cashbox Session" if you want to enforce cashbox session usage for that user
#. Users with this setting enabled must select a cashbox session when performing check transfers

**Cashbox Session Setup:**

#. Set up the cashboxes in **Accounting > Configuration > Cashbox Management**, including the destination journals of the transfers
#. Open the sessions from **Accounting > Bank and Cash > Cashbox**
#. A session of a restricted cashbox belongs to the users who operate it; a session of an unrestricted cashbox can be used by anyone

Usage
=====

**Mass Check Transfer with Cashbox Session:**

#. Navigate to **Accounting > Customers > Checks** or **Accounting > Vendors > Checks**
#. Select one or more third-party checks
#. Click "Transfer" button to open the mass transfer wizard
#. Select the destination journal
#. Select the cashbox session. The list shows the open sessions that the user can operate, of the cashboxes that handle the destination journal.
   If the user requires cashbox session usage, the field is mandatory
#. Complete the transfer - the outgoing payment of the transfer is linked to the selected cashbox session

**Security and Access Control:**

- The transfer button in the third party checks list is also available to invoicing users
- Cashbox session selection is filtered by user permissions and session status
- Only open sessions are available for selection

.. image:: https://odoo-community.org/website/image/ir.attachment/5784_f2813bd/datas
   :alt: Try me on Runbot
   :target: http://runbot.adhoc.com.ar/

Bug Tracker
===========

Bugs are tracked on `GitHub Issues
<https://github.com/ingadhoc/account-payment/issues>`_. In case of trouble, please
check there if your issue has already been reported. If you spotted it first,
help us smashing it by providing a detailed and welcomed feedback.

Credits
=======

Images
------

* |company| |icon|

Contributors
------------

Maintainer
----------

|company_logo|

This module is maintained by the |company|.

To contribute to this module, please visit https://www.adhoc.com.ar.
