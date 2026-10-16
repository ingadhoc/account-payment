=============
Payment Retry
=============

Charge customer invoices again with the customer's saved payment token, and keep the invoice flagged while that electronic payment is on course.

Características
===============

- Retry wizard, launched from the customer invoice list (**Actions › Retry payment**): one line per selected customer invoice or credit note that is posted, not paid or partially paid, with an amount due, of the current company and without an electronic payment on course.
- Each line proposes the most recent payment token of the customer (or of its contacts) and the amount due; the amount can be changed directly or as a percentage, for one line or for all of them.
- The wizard blocks the charge when a customer has no valid email, with a shortcut to the customers to fix.
- Before charging, the wizard looks for similar transactions of the same customers or tokens in the last days and shows them as a warning; the charge can still be created with **Create payments without check**. Payment providers can add their own check with a ``<provider code>_check_for_similar_transactions`` method on ``payment.token``.
- With more than 20 invoices, the payment requests are not sent at once: the scheduled action **Enviar transacciones de pago** sends them every 10 minutes.
- While an electronic payment is on course (transaction pending, authorized, or sent and waiting for the provider answer to be processed), the invoice shows the payment status **Electronic payment**, is not offered for online payment on the portal, and is not offered again in the retry wizard.
- Registering the payment by hand on such an invoice (**Pay**) first asks for confirmation and leaves an internal note on the invoice with the reference of the transaction on course.

Detalles Técnicos
=================

- New models:

  - ``payment.transaction.retry`` (transient): the retry wizard.
  - ``payment.transaction.retry.lines`` (transient): one line per invoice, with token, amount to pay and percentage.
  - ``electronic.payment.pending.confirm`` (transient): confirmation before registering a payment by hand.

- Inherited models:

  - ``account.move``: adds the ``electronic_pending`` value to ``status_in_payment``, the computed field ``has_pending_transaction``, and overrides ``_compute_status_in_payment``, ``action_force_register_payment`` and ``_has_to_be_paid``.
  - ``payment.transaction``: adds ``asynchronous_process``, the method ``cron_asynchronous_process`` and overrides ``_post_process_with_lock`` to leave the draft asynchronous transactions out of the post-processing.

- Views: form view of the retry wizard and of the confirmation wizard; server action **Retry payment** bound to the list view of ``account.move``.
- Data: scheduled action ``payment_asynchronous_process`` (every 10 minutes).
- Security: ``security/ir.access.csv`` gives full access to the three wizards to ``account.group_account_invoice``.
- System parameter ``payment_retry.similar_transactions_days_frame``: how many days back the similar transactions are looked for (default 1).

Uso
===

#. Go to the customer invoices list, select the invoices to charge and use **Actions › Retry payment**.
#. Check the proposed token and amount of each line; change the amount or the percentage if needed.
#. Click **Create payments**. If similar transactions are found, review the warning and click **Create payments without check** to go on.
#. The invoices show the payment status **Electronic payment** until the provider answer is processed; then they are paid, or released if the payment failed.
#. To check for similar transactions without charging, use **Check similar**.

Arquitectura
============

The wizard creates one ``offline`` payment transaction per line with a token and an amount, linked to its invoice. Without asynchronous processing it sends the payment request right away; with it, ``cron_asynchronous_process`` sends the draft transactions created in the last 4 days that are not sent yet. The provider answer is recorded as ``payment.data`` and processed by ``payment``'s processing cron; until then, ``account.move._get_pending_transactions`` counts the transaction as on course.

Dependencias
============

- ``account_payment``

Autor
=====

ADHOC SA

Licencia
========

LGPL-3
