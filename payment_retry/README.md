[![License: LGPL-3](https://img.shields.io/badge/license-LGPL--3-blue.png)](https://www.gnu.org/licenses/lgpl)

Payment Retry
=============

This module provides retry functionality for failed payment transactions in Odoo.

Features
--------

* **Asynchronous Processing**: Handle payment retries in the background
* **Manual Retry Wizard**: Allow users to manually retry failed transactions
* **Email Validation**: Validate partner email addresses before retry
* **Configurable Retry Limits**: Set retry time limits and frequency
* **Cron Job Integration**: Scheduled automatic retry processing

Installation
============

To install this module, you need to:

1. Add this module to your Odoo addons path
2. Update the apps list in Odoo
3. Install the module from Apps menu

Configuration
=============

After installation, the module will:

1. Add a scheduled action that runs every 10 minutes to process failed transactions
2. Add retry functionality to payment transactions
3. Create a wizard for manual retry operations

The cron job "Enviar transacciones de pago" will automatically process transactions in draft state with asynchronous_process flag enabled.

Usage
=====

Automatic Retry
---------------

The module automatically retries payment transactions that meet the following criteria:

* Transaction state is "draft"
* Operation is not "validation"
* Asynchronous process flag is enabled
* Transaction was created within the retry limit (default: 4 days)

Manual Retry
------------

Users can manually retry failed transactions using the Payment Transaction Retry wizard:

1. Go to payment transactions
2. Select failed transactions
3. Use the retry wizard to process them manually
4. Validate partner email addresses before retry
5. Configure retry percentage and add custom messages

Technical Details
-----------------

### Models Extended

* **payment.transaction**: Added asynchronous_process field and retry logic
* **account.move**: Enhanced for payment retry integration

### New Models

* **payment.transaction.retry**: Wizard for manual retry operations
* **payment.transaction.retry.lines**: Wizard lines for transaction details

### Scheduled Actions

* **Payment Asynchronous Process**: Runs every 10 minutes to retry failed transactions

Bug Tracker
===========

Bugs are tracked on GitHub Issues. In case of trouble, please check there if your issue has already been reported.

Credits
=======

Contributors
------------

* ADHOC SA

Maintainer
----------

This module is maintained by ADHOC SA.

For support and more information, please visit: https://www.adhoc.inc
