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

#. Ensure cashbox sessions are properly configured in **Accounting > Configuration > Point of Sale Sessions**
#. Create and open cashbox sessions as needed
#. Users can be assigned to specific sessions or left unassigned for global access

Usage
=====

**Mass Check Transfer with Cashbox Session:**

#. Navigate to **Accounting > Customers > Checks** or **Accounting > Vendors > Checks**
#. Select one or more third-party checks
#. Click "Transfer" button to open the mass transfer wizard
#. The system will automatically detect and suggest available cashbox sessions:

   - If only one session is open and accessible to the user, it will be pre-selected
   - If multiple sessions are available, a dropdown will allow selection
   - If the user requires cashbox session usage, the field becomes mandatory

#. Select the destination journal and cashbox session (if required)
#. Complete the transfer - all resulting payments will be linked to the selected cashbox session

**Security and Access Control:**

- The transfer button in check lists is restricted to users with "Show Accounting Features" access
- Cashbox session selection is filtered by user permissions and session status
- Only open sessions are available for selection

.. image:: https://odoo-community.org/website/image/ir.attachment/5784_f2813bd/datas
   :alt: Try me on Runbot
   :target: http://runbot.adhoc.com.ar/

Bug Tracker
===========

Bugs are tracked on `GitHub Issues
<https://github.com/ingadhoc/account_payment/issues>`_. In case of trouble, please
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
