.. |company| replace:: ADHOC SA

.. |company_logo| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-logo.png
   :alt: ADHOC SA
   :target: https://www.adhoc.com.ar

.. |icon| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-icon.png

.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

=======================
Account Payment Pro HTL
=======================

In a new payment, the standard behavior raises the amount up to the selected debt
every time debt lines are added or removed. With this module, the amount loaded by
the user, by the checks or by an integration is kept, and the difference is shown.

A lock next to the amount controls it on each new payment. It starts locked; unlock
it to get the standard behavior back on that payment.

With the lock closed, the amount still follows the debt only while it was proposed
by the system:

#. The amount is zero (for example, right after choosing the partner).
#. The amount is the one proposed by "Register Payment" from an invoice, so the
   currency rate correction keeps working.

Known limitation: if the user types the same amount that "Register Payment"
proposed, it is taken as proposed and it still follows the debt.

Installation
============

To install this module, you need to:

#. Install it from Apps. It is not auto-installed.

**Important:** the module applies to the whole database. In a database with several
companies, new payments start locked in all of them; it can't be enabled for only one
company.

Configuration
=============

No configuration is needed.

Usage
=====

To use this module, you need to:

#. Have the setting 'Use payment pro module' activated for your company.
#. Create a new customer or vendor payment, load the amount and then add or remove
   debt lines: the amount doesn't change.
#. To let the amount follow the debt on that payment, click the lock next to the
   amount before changing the debt lines.

The lock is shown only on new payments: a saved draft payment never changes its
amount when the debt changes, locked or not.

Supplier payments with automatic withholdings are out of scope: the withholdings
still adjust the amount.

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
