{
    "name": "Account Payment Register - Force Rate",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "summary": "Force exchange rate when registering payment on foreign currency invoices",
    "description": """
When registering a payment from a foreign currency invoice using the standard
payment register wizard, this module adds an editable exchange rate field
(amount in company currency) so the user can override the system rate.

Without this module, the wizard uses the automatic rate from res.currency.rate
and there is no way to change it.
    """,
    "author": "BMYA",
    "license": "AGPL-3",
    "depends": ["account"],
    "data": [
        "views/account_payment_register_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
