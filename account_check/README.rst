Descripción de la nueva propuesta:
    La idea es hacerlo más a la odoo way, por ej:
        https://www.odoo.com/documentation/user/9.0/accounting/receivables/customer_payments/check.html
        https://www.odoo.com/documentation/user/9.0/accounting/payables/pay/check.html
        https://www.odoo.com/documentation/user/9.0/accounting/bank/misc/batch.html
    Entonces proponemos hacer un cheque un account.payment
    La idea sería:
        1. Crear diario tipo "cash" con Debit Methods y payment methods "Third Check"
            TODO que la cuenta que se crea sea reconciliable y que no deje elegir manual tmb
        2- Luego el cheque:
            a) se puede usar para pagar
            a) se puede usar para depositar
    Para cheques de terceros:

TODO:
Podemos tratar de hacer que el cheque en si sea el apunte contable. De esta manera es mas facil dar de alta datos inciales y no dependemos de cambios de objetos ni nada.

Tratamos de mantener la logica de https://www.odoo.com/documentation/user/9.0/accounting/receivables/customer_payments/check.html


# Account Check Management

## Resumen de circuitos y operaciones:

### Cheques de terceros depositado
Cobro (account.voucher) / diario "Cheques de terceros" / Estado "En mano"
* Valores en cartera
*       a deudores x venta

#### Deposito y rechazo
Depósito (account.move) / diario "Bancos" / Estado "Depositado"
* Banco
*       a Valores en cartera

Rechazo (account.move) / diario "Bancos" / Estado "Rechazado"
* valores rechazadods   500
* gastos                100
*       a Bancos            600

Nota de débito (ND) / 
* deudores x venta    600
*       a gastos              100
*       a valores rechazadods 500

#### Entrega y rechazo
Pago a proveedor (PAGO)
    proveedores
        a valores en cartera

Rechazo cheque pasado (nota de debito)
    valores rechazados
    gasto
        a proveedores

Nota de debito a cliente (idem arriba)
    deudores x venta    600
        gastos                100
        a valores rechazadods 500

#### Devolución
TODO

#### Cambio
TODO


VALORES PROPIOS

PAGO
    proveedores
        a cheques dif

DEBITO
    cheq dif
        a banco

RECHAZO Nota de débito
    cheques dif
    gastos
        a proveed




Debito
    cheq dif
        a banco

Rechazo (ASIENTO DE RECHAZO)
    banco
        a valores propios rechazados
    (aca podriamos agregar el gasto bancario tmb=)






Rechazo 
Valores 3ros rechazados
    a valores en cartera



Rechazo cheque pasado
    Marco cheque como rechazado
        Valores 3ros rechazados
            a proveedores
