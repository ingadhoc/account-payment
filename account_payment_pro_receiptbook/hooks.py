from odoo.addons.account.wizard.account_resequence import ReSequenceWizard


def _revert_method(cls, name):
    """Revertir el método original llamado 'name'"""
    method = getattr(cls, name)
    origin = getattr(method, "origin", None)
    if origin:
        setattr(cls, name, origin)


def uninstall_hook(env):
    _revert_method(ReSequenceWizard, "default_get")
