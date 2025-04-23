{
    'name': "Card installment",
    'description': """
        Base module for compute installment and fee on creditcard sales method
    """,
    'author': 'ADHOC SA',
    'website': "https://www.adhoc.com.ar",
    'category': 'Technical',
<<<<<<< HEAD
    'version': "17.0.1.0.0",
||||||| parent of e351fdbe (temp)
    'version': "16.0.1.0.0",
=======
    'version': "16.0.1.1.0",
>>>>>>> e351fdbe (temp)
    'depends': ['product', 'account'],
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
        'views/card_installment_view.xml',
    ],
    'demo': [
        'demo/product_product.xml',
        'demo/account_card.xml',
    ],
}
