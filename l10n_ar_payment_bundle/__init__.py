from . import models  # noqa: F401


def post_init_hook(env):
    companies = env["res.company"].search([("active", "=", True), ("use_payment_pro", "=", True)])
    companies._create_payment_bundle_journal_if_needed()
