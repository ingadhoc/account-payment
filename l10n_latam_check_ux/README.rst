.. |company| replace:: ADHOC SA

.. |company_logo| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-logo.png
   :alt: ADHOC SA
   :target: https://www.adhoc.com.ar

.. |icon| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-icon.png

.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

==============
Latam Check UX
==============

This module extends the standard functionality of Odoo's l10n_latam_check module with the following features:

* Debit checks from payments: Adds a button in the check record to perform the debit action, streamlining check management.
* Check number in PDF documents: Includes the check number when printing the receipt and payment PDFs, improving traceability.
* Journal entry protection: The journal entry of a payment with checks cannot be deleted while the payment is confirmed, because deleting it and posting the payment again leaves the check with the wrong current journal. The payment has to be reset to draft to adjust its journal entry.
* Own checks with automatic debit: when the account configured on the own checks payment method is not reconcilable (typically the liquidity account of the journal itself, i.e. the bank debits the check as soon as it is issued), the check is always in debited state and no reconciliation can ever move it. Those payments can be reset to draft and cancelled: the core restriction protects the reconciliation that debited or voided the check, and here there is none.

Installation
============

To install this module, you need to:

#. Nothing to do

Configuration
=============

To configure this module, you need to:

#. Nothing to do

Usage
=====

To use this module, you need to:

.. image:: https://odoo-community.org/website/image/ir.attachment/5784_f2813bd/datas
   :alt: Try me on Runbot
   :target: http://runbot.adhoc.com.ar/

Bug Tracker
===========

Bugs are tracked on `GitHub Issues
<https://github.com/ingadhoc/odoo-argentina/issues>`_. In case of trouble, please
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
