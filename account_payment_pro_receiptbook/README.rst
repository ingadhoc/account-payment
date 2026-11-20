.. |company| replace:: ADHOC SA

.. |company_logo| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-logo.png
   :alt: ADHOC SA
   :target: https://www.adhoc.com.ar

.. |icon| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-icon.png

.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

===========================
Account Payment receiptbook
===========================

Adds receiptbooks to the payments of Account Payment Pro. A receiptbook gives
customer receipts and vendor payment orders their own numbering, like a
document (for example ``RE-X 0001-00000001``), separate from the numbering of
the bank or cash journal.

Features
========

* Receiptbooks by company and partner type (customer or vendor), each one with
  a document type, a prefix and its own sequence. The sequence can be standard
  or "no gap".
* Two document types: "RECIBOS X" (``RE-X``) for customer receipts and
  "ORDEN DE PAGO X" (``OP-X``) for vendor payments.
* When a payment is posted, it takes its number from the receiptbook, and the
  journal entry gets the same name and the document type of the receiptbook.
  Canceled payments do not take a number.
* Payments cannot be posted with an archived receiptbook or with a receiptbook
  without a sequence.
* Optional email template, sent to the partner when the payment is posted, and
  optional partner for the header of the printed receipt.
* Other entries of the same bank or cash journal keep the journal numbering and
  never take a number from a receiptbook.
* Sequence gaps (``made_sequence_gap``) are checked by receiptbook and prefix,
  not by journal.
* Branches: the combination of prefix, document type and partner type is unique
  across a company and its branches. A branch gets the first free prefix
  (``0002-``, ``0003-``, ...). With more than one active company, the name of a
  receiptbook of a company with branches shows its company.
* The Resequence wizard of journal entries works by receiptbook: it can
  resequence entries of the same receiptbook from different journals, does not
  mix receiptbooks or entries with and without receiptbook, checks that the new
  names are not used and then updates the next number of the receiptbook.
* A used receiptbook (with posted payments) cannot be deleted.

Installation
============

To install this module, you need to:

#. Just install this module. Receiptbooks for customers and vendors are created
   in every company with a chart of accounts, and later in each new company
   when its chart of accounts is loaded.

Configuration
=============

To configure this module, you need to:

#. Go to Accounting > Configuration > Settings and enable "Use Receiptbook".
   It needs "Use Payment Pro", and it is enabled by default for Argentinean
   companies that use Payment Pro.
#. Go to Accounting > Configuration > Receiptbooks to review or create
   receiptbooks: name, partner type, document type, prefix, next number,
   sequence implementation, email template and report partner.

Usage
=====

To use this module, you need to:

#. Create a customer or vendor payment. The receiptbook of the company and
   partner type is set by default, and it can be changed while the payment is
   in draft.
#. Post the payment: it is numbered with the receiptbook sequence.
#. To resequence receipts, enable the developer mode, select the journal
   entries of one receiptbook in the list view and use Action > Resequence.

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
