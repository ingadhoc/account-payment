from odoo.addons.account.wizard.account_resequence import ReSequenceWizard


def _revert_method(cls, name):
    """Revertir el método original llamado 'name'"""
    method = getattr(cls, name)
    setattr(cls, name, method.origin)


def uninstall_hook(cr, registry):
    _revert_method(ReSequenceWizard, "default_get")
