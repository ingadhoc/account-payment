.. image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
   :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
   :alt: License: AGPL-3

==============
Payment Groups
==============

This module extends the functionality of payments to suport paying with multiple payment methods at once.

By default payments are managed on one step, if you want, you can use two steps to confirm payments on supplier payments. This option is available per company.

MEJORAS
    agregar pra generar notas de credito desde cobro 

TODO

Ver proble ade redonde con match y unmath, ejemplo http://localhost:9069/web?debug#id=35&view_type=form&model=account.payment.group&menu_id=174&action=231
Con double validation, en pago de factura de proveedores, ocultar pestana y ver que quede bien lo de notes
Al generar un pago a proveedor, poner foco en pestana To Pay Lines, en lugar de Notes
NTH Boton para ir a facturas pagada en Pagos

ver como hcacemos pagos de deuda de otra moneda y motnos fincnaiceros y demas
eliminar menu de acion mas de registrar pago individual
Corregir talonarios de recibo que no dependen del payment type si no de si es proveedor o cliente
arreglar transferencias internas que exigen recibo
300
500

Mejorar debt management que no haga falta mostrar campo currency al usar widget y ver si hay que filtrar cosas conciliadas


que debt managemnt no active por defecto importes financiaeros

NOTAS
    cliente o provedeor define la cuenta que va ausar (ds o prov) y el dominio de partners a mostrar


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
   :target: https://runbot.adhoc.com.ar/

.. repo_id is available in https://github.com/OCA/maintainer-tools/blob/master/tools/repos_with_ids.txt
.. branch is "8.0" for example

Known issues / Roadmap
======================

* ...

Bug Tracker
===========

Bugs are tracked on `GitHub Issues
<https://github.com/ingadhoc/{project_repo}/issues>`_. In case of trouble, please
check there if your issue has already been reported. If you spotted it first,
help us smashing it by providing a detailed and welcomed feedback.

Credits
=======

Images
------

* ADHOC SA: `Icon <http://fotos.subefotos.com/83fed853c1e15a8023b86b2b22d6145bo.png>`_.

Contributors
------------


Maintainer
----------

.. image:: http://fotos.subefotos.com/83fed853c1e15a8023b86b2b22d6145bo.png
   :alt: Odoo Community Association
   :target: https://www.adhoc.com.ar

This module is maintained by the ADHOC SA.

To contribute to this module, please visit https://www.adhoc.com.ar.
