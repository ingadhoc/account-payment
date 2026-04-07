# SOBRE COUNTERPART CURRENCY

1. counterpart_currency_id
solo lo seteabamos en algunos casos. y como ahora es requerido queremos que esté en todos los casos. Casos:
a) estaba definida y era distinta a currency_id, pero currency_id = company_currency_id --> caso normal (pago en ARS, counterpart en USD). el rate estaba bien almacenado.
b) estaba definida y era distinta a currency_id pero currency_id era distinto a company_currency_id. EN este caso a nivel asiento se ignoraba la counterpart_currency_id y se usaba solo currency_id, por lo cual a la hora de migrar la idea es alinear el dato (counterpart_currency_id = currency_id y rate = 1)
c) Si no estaba definido, que debe ser la mayoría de los casos, el Counterpart real vendría a ser la moneda del diario (si estaba definida) o, básicamente, la moneda de la compañía (use o no use reconcile)
d) en las transferencias nunca se definida si era False y counterpart_exchange_rate 0 (o null en base de datos, no lo verificamos). En la nueva versión aprovechamos este campo para representar la omneda del diario de destino. 

Decisiones para migración:
1.1) tratamos de computar este valor en todos los payments? hay que tener en cuenta muchas cosas porque a la larga lo más real es lo que está en el asiento. 
1.2) no la computamos y no la hacemos requerida por vista (salvo en estado borrador) para que tengamos compatibilidad hacia atrás? podríamos computar solo pagos en draft? 

2. counterpart_rate
antes se llamaba counterpart_exchange_rate, lo estamos calculando como el inverso de counterpart_rate. Si vamos por 1.2 podemos dejar que solo se migre donde estaba el dato y no nos preocupamos por valores en 0.

3. counterpart_currency_amount
no era almacenado, lo estamos calculando con el dato de amount * counterpart_rate
en los casos donde no teníamos definido counterpart_currency_id, este campo no debe estar definido. si hacemos
1.1) tendríamos que computarlo
1.2) lo podríamos ocultar

# SOBRE ACCOUNTING RATE
4. En cuanto al accounting_rate y al force_amount_company_currency. Si
El accounting_rate se calculaba habitualmente on-the-fly según la cotización de la compañía a la fecha, a menos que alguien hubiera forzado un valor, el cual quedaba expresado en force_amount_company_currency.
4.a) Si existe un valor en force_amount_company_currency, el accounting_rate se obtiene dividiendo ese monto forzado por el amount.
4.b) si no existe (se había utilizado rate de sistema), tenemos estas alternativas:
4.b.1) no mostrar ni computar el rate 
4.b.2) computar el rate desde el historico de monedas (es como lo hacía la UI anteriormente, calculaba on de fly según cotización) 
4.b.3) calcular desde los apuntes contables, solo factible si están 


# write_off_amount
5. write_off_amount
estaba expresado en company_currency_id, ahora es en destination_currency_id

6. unreconciled_amount
se debe dar vuelta el signo en algunos casos tal como está implementado en el migration script, ya lo validamos


Campos que tenemos que computar:
* counterpart_rate
* counterpart_currency_id (Según definamos si lo hacemos para todos o solo los que estaban definidos)
* accounting_rate
* unreconciled_amount
* write_off_amount
