.. |company| replace:: ADHOC SA

.. |company_logo| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-logo.png
   :alt: ADHOC SA
   :target: https://www.adhoc.com.ar

.. |icon| image:: https://raw.githubusercontent.com/ingadhoc/maintainer-tools/master/resources/adhoc-icon.png

.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

==============================
Secondary currency on payments
==============================

On future versions this module will be merged on standard module.

Nativamente en Odoo, el campo moneda de los pagos se utiliza para dos cosas:
a) representar que a nivel liquidez el pago es en esa moneda
b) representar que a nivel deuda se canceló un determinado importe en esa moneda

En mi opinión esto no es del todo correcto. Tiene algunos inconvenientes como:
a) En diarios en moneda de compañía, si quiero representar cancelar un determinado monto en una divisa (por ej. porque cuenta deudora tiene esa divisa), tengo que forzar representa que en liquidez tmb pago con esa divisa. Esto es extraño en cualquier diario, pero más aún en cuestiones como retenciones y en en casos de cheques se vuelve problemático porque me queda representado que el cheque es de una divisa y luego tengo problemas al endosarlo. Por ej, recibo un cheque de 1000 ARS que cancelan 1 USD. Para representarlo tengo que elegir moneda USD y luego el cheque ya queda como que es en USD, cuando lo quiera usar para pagar a un proveedor se va a considerar un cheque de 1 USD pero en realidad es un cheque de 1000 ARS.
b) No puedo en odoo cancelar deuda en una divisa cobrando con otra divisa. Por ejemplo, mi compañía está en pesos pero cobro 100 EUR para cancelar 105 USD.

Creo que lo ideal sería que Odoo:
a) use la moneda del pago para la línea de contrapartida (AP/AR)
b) use la moneda del diario para la línea de liquidez
c) use exchange rates de monedas o, idealmente, permita forzar distintos en el pago.

Por ahora hacemos este cambio agregando nuevos capos porque parece ser lo más facil. Cambiar como interpretamos el campo moneda de odoo es facil en payment pero complicado porque hay otros modulos que interpretan la currency del pago como la currency de liquidez (por ej. cheques)

Installation
============

To install this module, you need to:

#. Do this ...

Configuration
=============

To configure this module, you need to:

#. Go to ...

Usage
=====

To use this module, you need to:

#. Go to ...

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
