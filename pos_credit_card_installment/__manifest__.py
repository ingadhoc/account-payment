# -*- coding: utf-8 -*-
{
    "name": "Implent in pos credit card installment",
    "summary": "",
    "description": """""",
    "author": "Axcelere",
    "website": "http://www.axcelere.com",
    "category": "pos",
    "version": "16.0.0.1",
    "depends": ['card_installment'],
    "data": [
        "views/pos_payment_method.xml",
    ],
    'assets': {
        'point_of_sale.assets': [
            'pos_credit_card_installment/static/src/css/pos_card_cart_installment.css',
            'pos_credit_card_installment/static/src/js/**/*.js',
            'pos_credit_card_installment/static/src/xml/**/*.xml',
        ],
    },
    "qweb": [
        "static/src/xml/card_instalment.xml",
    ],
}
