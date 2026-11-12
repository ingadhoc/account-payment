=============================================
Sale Exception Credit Limit - Latam Checks
=============================================

Bridge module between ``sale_exception_credit_limit`` and ``l10n_latam_check_ux``:
the credit taken of the partner includes the third party checks on hand, and the
credit limit warning counts them only once.

Features
========

- When **Include Third Party Checks on Hand** is enabled in the accounting settings,
  **Credit Taken** (``credit_with_confirmed_orders``) adds the third party checks on hand
  of the partner, converted to the company currency, on top of the debt, the confirmed
  orders to invoice and the draft invoices.
- The credit limit warning on invoices and sales orders, and therefore the credit limit
  sale exception, includes the checks once, with a line that shows their amount.
- Installs automatically (``auto_install``) only when both base modules coexist.

Technical Details
=================

- New models: none.
- Inherited models: ``res.partner``, ``account.move``.
- ``res.partner._compute_credit_with_confirmed_orders``: adds
  ``_get_on_hand_checks_credit`` (``l10n_latam_check_ux``) when the partner has its own
  credit limit, the same condition the base compute uses.
- ``account.move._build_credit_warning_message``: ``sale_exception_credit_limit`` builds
  the total from the credit taken, which already carries the checks, so it calls super
  with ``checks_in_credit`` in the context to keep ``l10n_latam_check_ux`` from adding
  them again, and adds the line that explains them.
- Views / data / security: none.

Usage
=====

1. Go to **Accounting → Configuration → Settings** and enable **Sales Credit Limit**
   and **Include Third Party Checks on Hand**.
2. Set a credit limit on the customer.
3. **Credit Taken** and the credit limit warning include the checks received from the
   customer that are still on hand.

Dependencies
============

- ``sale_exception_credit_limit``
- ``l10n_latam_check_ux``

Author
======

ADHOC SA

License
=======

AGPL-3
