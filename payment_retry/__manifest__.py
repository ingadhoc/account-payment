{
    'name': "payment retry",
    'description': """
        Retry payment from account move lines.
    """,
    'author': 'ADHOC SA',
    'website': "https://www.adhoc.inc",
    'category': 'Payment',
    'version': "17.0.1.0.0",
    'depends': ['account'],
    'license': 'LGPL-3',
    'images': [
    ],
    'installable': True,
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'wizards/payment_transaction_retry.xml',
    ],
}

