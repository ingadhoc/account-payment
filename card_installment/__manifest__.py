{
    'name': "Card installment",
    'description': """
        Base module for compute installment and fee on creditcard sales method
    """,
    'author': 'ADHOC SA',
    'website': "https://www.adhoc.com.ar",
    'category': 'Technical',
    'version': '15.0.0.0.1',
    'depends': ['product'],
    'license': 'LGPL-3',
    'images': [
    ],
    'installable': True,
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/account_card.xml',
        'data/decimal_installment_coeficent.xml',
        'views/account_card.xml',
    ],
    'demo': [
        'demo/product_product.xml',
        'demo/account_card.xml',
    ],
}

