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
