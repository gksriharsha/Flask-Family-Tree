"""Small decorators.

The originals were named ``cached`` and ``log_this`` but defined ``def wrapper():`` with no
``*args``/``**kwargs`` and no ``return``, so they could not accept arguments and discarded the
wrapped function's result. Anything they were applied to would have broken -- which is why
nothing used them.
"""

import functools
import logging
import time

log = logging.getLogger(__name__)


def cached(function):
    """Memoise on the call arguments. Only safe for pure functions with hashable arguments."""
    return functools.lru_cache(maxsize=256)(function)


def log_this(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            log.debug('%s took %.1f ms', function.__qualname__,
                      (time.perf_counter() - started) * 1000)

    return wrapper
