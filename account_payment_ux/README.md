[![Code Climate](https://codeclimate.com/github/ingadhoc/account-payment/badges/gpa.svg)](https://codeclimate.com/github/ingadhoc/account-payment)

# ADHOC Account Payment UX

- Block new payments on the same related invoice, once it has a pending transaction in process. Unlike Odoo, this applies to the pending transactions of any provider, bank transfers included.

- Hide from the portal overdue invoices the invoices with a pending transaction.

- When the electronic transaction is pending the payment will remain in draft status. After done this electronic transaction the payment changes its state and reconcilie with the invoices.

- When a confirmed transaction goes to error or is cancelled, Odoo cancels its payment. If the transaction is confirmed again, the same payment is posted and reconciled with the invoices.

----

<img alt="ADHOC" src="http://fotos.subefotos.com/83fed853c1e15a8023b86b2b22d6145bo.png" />
**Adhoc SA** - www.adhoc.com.ar
