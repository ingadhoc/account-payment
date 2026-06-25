# TEMP DEBUG - remove before merge. Logs the stacktrace of every registry
# cache invalidation to find which code path triggers it during the payments
# list load.
import logging
import traceback

from odoo.modules.registry import Registry

_logger = logging.getLogger("CLEARCACHE_DEBUG")

if not getattr(Registry, "_cc_debug_patched", False):
    _orig_clear_cache = Registry.clear_cache

    def _traced_clear_cache(self, *cache_names):
        _logger.warning(
            "CLEARCACHE_DEBUG names=%s\n%s",
            cache_names,
            "".join(traceback.format_stack()[-18:]),
        )
        return _orig_clear_cache(self, *cache_names)

    Registry.clear_cache = _traced_clear_cache
    Registry._cc_debug_patched = True
