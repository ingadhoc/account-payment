.. |company| replace:: ADHOC SA

.. |company_logo| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-logo.png
   :alt: ADHOC SA
   :target: https://www.adhoc.com.ar

.. |icon| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-icon.png

.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

================
Account Cashbox
================

Comprehensive cash management module for Odoo that provides complete cashbox session control, payment tracking, and cash reconciliation features.

Features
========

* **Cashbox Configuration Management**: Set up and configure multiple cashboxes with custom settings
* **Cash Session Control**: Start, manage, and close cashbox sessions with proper validation
* **Payment Integration**: Seamlessly handle cash payments through cashbox sessions
* **User Session Requirements**: Enforce cashbox session requirements for specific users
* **Rounding Adjustments**: Handle cash rounding differences with dedicated adjustment tools
* **Payment Import**: Import and process multiple payments within cashbox sessions
* **Move Integration**: Link accounting moves to cashbox sessions for complete traceability

Installation
============

To install this module, you need to:

#. Just install this module.

Dependencies
============

* account_ux
* account_internal_transfer

Configuration
=============

Cashbox Setup
-------------

#. Go to **Accounting > Configuration > Cashbox Management**
#. Create new cashboxes and configure:

   * Name and description
   * Associated journal
   * Session validation rules
   * User permissions

User Configuration
------------------

#. Go to **Settings > Users & Companies > Users**
#. For users that require cashbox sessions:

   * Enable "Require Cashbox Session"
   * Assign appropriate cashbox access rights

Usage
=====

Daily Cash Operations
---------------------

**Starting a Session:**

#. Go to **Accounting > Bank and Cash > Cashbox**
#. Select your cashbox and click "New Session"
#. Click in "Open Session"

**Processing Payments:**

#. Cash payments will automatically link to active sessions
#. Use **Payment Import Wizard** for bulk payment processing:

   * Go to active session
   * Click "Import Payments"
   * Upload or enter payment data

**Session Management:**

#. Monitor ongoing sessions from the Cash Sessions menu
#. Track payments, adjustments, and balances in real-time
#. Use session lines to review all transactions

**Closing a Session:**

#. Count physical cash and enter closing balance
#. Use **Rounding Adjustment** wizard if needed:

   * Click "Rounding Adjustment" in session
   * Enter actual counted amount
   * System calculates and posts adjustment

#. Validate session closure

Payment Registration
--------------------

When registering payments in invoices:

#. The system will check if user requires cashbox session
#. Active sessions will be automatically linked to cash payments
#. Session validation ensures all cash goes through proper controls

Accounting Integration
----------------------

#. All cashbox operations create proper accounting entries
#. Session movements are linked to accounting moves
#. Full traceability from payment to journal entries
#. Automatic reconciliation with bank statements

Technical Details
=================

Models Extended
---------------

* `account.payment` - Links payments to cashbox sessions
* `account.move` - Adds cashbox session tracking
* `res.users` - Adds cashbox session requirements
* `account.payment.register` - Integrates session validation

New Models
----------

* `account.cashbox` - Cashbox configuration
* `account.cashbox.session` - Cash session management
* `account.cashbox.session.line` - Session transaction lines

Wizards
-------

* Payment Import - Bulk payment processing
* Rounding Adjustment - Handle cash differences
* Enhanced Payment Register - Session-aware payment registration

Security
========

The module includes comprehensive security rules:

* Cashbox access controls
* Session user restrictions
* Payment validation rules
* Multi-company support

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
