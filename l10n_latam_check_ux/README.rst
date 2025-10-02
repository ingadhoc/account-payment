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

This module extends the standard functionality of Odoo's l10n_latam_check module with enhanced user experience features for Latin American check management. It provides comprehensive improvements for check operations, reporting, and workflow optimization.

**Version:** 19.0.1.0.0

Features
========

Check Operations Management
---------------------------

* **Check Debit Functionality**: Adds a "Debit check" button on check records allowing users to easily debit checks with outstanding balances.
* **Enhanced Check Operations**: Improved check operation tracking with operation dates and better filtering of operations by company.
* **Check Operation History**: Complete operation tracking with chronological ordering and proper company filtering.
* **Reset to Draft Validation**: Prevents resetting payments to draft if they are not the last operation for the associated checks.


Mass Transfer Operations
------------------------

* **Enhanced Mass Transfer Wizard**: Improved wizard for transferring multiple checks between journals with additional validation.
* **Split Payment Option**: Ability to create individual payments for each check instead of grouping them into a single payment.
* **Inter-company Transfer Validation**: Proper validation for transfers between different companies and branches.
* **Automatic Pairing**: Automatic creation and pairing of inbound/outbound payments for internal transfers.

User Interface Enhancements
----------------------------

* **Extended Check Views**: Additional fields in check list views including payment date, memo, and operation dates.
* **Advanced Filtering**: New filters like "Last 90 days" for better data navigation.
* **Operation Date Display**: Visible operation dates in check operation trees for better tracking.
* **Bulk Actions**: Support for bulk check debit operations from list views.

Data Management
---------------

* **Operation Date Tracking**: Automatic tracking of operation dates with proper sequencing for check operations.
* **Company Context**: Improved company handling for multi-company environments.
* **Check State Validation**: Enhanced validation to ensure check operation integrity and proper state transitions.

Technical Features
==================

Models Extended
---------------

* **l10n_latam.check**: Enhanced with debit button configuration, operation dates, company computation, and payment state tracking.
* **account.payment**: Extended with operation date tracking, validation improvements, and enhanced internal transfer functionality.
* **account.journal**: Added check debit button configuration field.

New Wizards
-----------

* **account.check.action.wizard**: Wizard for check debit operations with date validation and outstanding account management.
* **l10n_latam.payment.mass.transfer**: Enhanced mass transfer wizard with split payment functionality and inter-company validation.

Security & Permissions
----------------------

* Access rights defined in ``security/ir.model.access.csv`` for proper wizard access control.

Validation & Constraints
-------------------------

* Date validation ensuring debit dates are not before issue dates.
* Company validation for mass transfer operations.
* Outstanding account validation for debit operations.
* Check operation sequence validation.

Installation
============

This module has the following dependencies:

* ``l10n_latam_check``: Base Latin American check functionality
* ``account_ux``: Account user experience enhancements
* ``account_internal_transfer``: Internal transfer functionality

To install this module:

#. Ensure all dependencies are installed and updated
#. Install the module through the Apps menu
#. The module will auto-install if all dependencies are present

Configuration
=============

Journal Configuration
---------------------

#. Go to **Accounting → Configuration → Journals**
#. Open a journal used for check management
#. In the **Latam Checks** section, enable **"Agregar botón de débito"** to allow check debit operations
#. Ensure the journal has a manual payment method configured for debit operations

Payment Method Setup
--------------------

#. Verify that journals have proper payment methods configured:

   * For outbound payments: Manual payment method for debit operations
   * For check transfers: Appropriate third-party check payment methods

#. The system will automatically use:

   * Manual payment method named "Manual" if available
   * First available manual payment method as fallback

Usage
=====

Check Debit Operations
----------------------

#. Navigate to **Accounting → Vendors → Checks** or **Accounting → Customers → Checks**
#. Open a check record in "Handed" state
#. Click the **"Debit check"** button (visible only if journal is configured for debit operations)
#. Set the debit date (must be after the check issue date)
#. Confirm the operation

The system will:

* Create a reconciliation entry using the configured outstanding account
* Post a message on the check record with the debit operation details
* Link the debit move for audit trail

Mass Check Transfers
--------------------

#. Go to **Accounting → Vendors → Checks** or use the check transfer wizard
#. Select multiple checks for transfer
#. Choose destination journal
#. Enable **"Split Payment"** if you want individual payments per check
#. Confirm the transfer operation

The system will:

* Validate that all checks belong to the same company
* Create appropriate internal transfer payments
* Maintain proper operation sequencing and dates
* Link outbound and inbound payments automatically

Enhanced Reporting
------------------

Payment receipts and transfer reports will automatically include:

* Check numbers
* Bank information (for third-party checks)
* Issuer VAT information (for third-party checks)
* Payment dates
* Amounts with proper currency formatting

Advanced Filtering
------------------

Use the enhanced filters in check views:

* **Last 90 days**: Quick filter for recent checks
* **Payment State**: Filter by payment status
* **Company**: Multi-company filtering support

Known Issues & Limitations
===========================

* Check debit operations require proper manual payment method configuration in the journal
* Mass transfers between different companies require appropriate permissions and company context
* Split payment functionality is only available for third-party checks with compatible currencies

Troubleshooting
===============

Common Issues
-------------

**"No es posible crear un nuevo débito de cheque sin un método de pagos 'manual' en el diario"**

* Solution: Configure a manual payment method in the journal settings

**"At least one check is in a journal where the 'Add Debit Date' option is not enabled"**

* Solution: Enable the "Agregar botón de débito" option in the journal configuration

**"Operation not allowed: To transfer the checks, you must be operating in the same company"**

* Solution: Switch to the appropriate company context before performing the transfer

**"All selected checks must belong to the same company"**

* Solution: Select checks from the same company for mass transfer operations

Technical Notes
===============

Migration Notes
---------------

* Migration scripts are available in ``migrations/18.0.1.6.0/`` for version upgrades
* The module maintains compatibility with Odoo 19.0 and includes auto-install capability

Data Files
----------

* ``security/ir.model.access.csv``: Access control definitions
* ``views/``: All view modifications and enhancements
* ``wizards/``: Wizard definitions and forms
* ``reports/``: Enhanced report templates
* ``i18n/es.po``: Spanish translations

Development & Extending
========================

The module follows Odoo best practices and can be extended by:

* Inheriting the provided models for additional functionality
* Adding new wizards for custom check operations
* Extending report templates for additional check information
* Creating additional validation rules through model constraints

Example of extending check debit functionality::

    from odoo import models, fields

    class CustomCheckExtension(models.Model):
        _inherit = 'l10n_latam.check'

        custom_field = fields.Char('Custom Field')

        def custom_debit_action(self):
            # Custom debit logic here
            return super().action_confirm()

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

* ADHOC SA Development Team

Maintainer
----------

|company_logo|

This module is maintained by |company|.

To contribute to this module, please visit https://www.adhoc.com.ar.
