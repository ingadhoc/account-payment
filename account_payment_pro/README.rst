.. |company| replace:: ADHOC SA

.. |company_logo| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-logo.png
   :alt: ADHOC SA
   :target: https://www.adhoc.com.ar

.. |icon| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-icon.png

.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

===================
Account Payment Pro
===================

This module is designed to enhance and extend the functionality of Odoo's core payment models. This module is essential for managing withholdings in Argentina.

**To manage Argentina withholdings it's mandatory to have "l10n_ar_withholding" module installed.**

Functionalities
===============

This module provides advanced payment capabilities:

* **Select Debts to Pay**: Users can choose specific debts to settle during the payment process.
* **Manage Withholdings Calculation**: The module facilitates the calculation of withholdings as part of the payment processing.
* **Register Write-Offs**: Users can register write-offs directly within the payment.
* **Immediate Payment Option in Invoices**: Provides a "Pay Now" feature for instant payment processing from invoices.
* **Argentina Withholding Support**: When combined with the "l10n_ar_withholding" module, enables a dedicated withholdings tab for managing Argentina-specific tax withholdings.

Installation
============

To install this module, you need to:

#. Install the "account_ux" module
#. For Argentina withholding features, install the "l10n_ar_withholding" module

Configuration
=============

To configure this module, you need to:

#. Go to Accounting > Configuration > Write-off Types to configure write-off types
#. Go to Accounting > Configuration > Settings > Payment to configure payment settings

Usage
=====

To use this module:

#. Go to Accounting > Payments to create and manage payments
#. Use the "Pay Now" button on invoices for quick payment processing
#. Select specific debts to pay when creating a payment
#. Register withholdings and write-offs directly in the payment form
#. For Argentina withholdings: ensure "l10n_ar_withholding" is installed to access the withholdings tab

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
