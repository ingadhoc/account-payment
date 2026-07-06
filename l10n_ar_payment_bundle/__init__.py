<<<<<<< 8be1185b7e06b1df2ccbb18a22192ee2d2920a60
from . import models
from . import wizard
from . import demo
||||||| 72a9ba0ce57af6cbdd07099e3eb745b36c14b96a
from . import models  # noqa: F401
=======
from . import models  # noqa: F401
from . import wizard  # noqa: F401
>>>>>>> 22df653f8ced539657ef982011e42b2aaf1466be


def post_init_hook(env):
    companies = env["res.company"].search([("active", "=", True), ("use_payment_pro", "=", True)])
    companies._create_payment_bundle_journal_if_needed()
