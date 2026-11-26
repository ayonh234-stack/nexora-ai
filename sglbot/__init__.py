"""Nexora AI Telegram chatbot."""

__version__ = "1.0.0"


def _preload_fribidi() -> None:
    """Pillow shapes Bengali (raqm) only if libfribidi can be dlopen'ed; serverless images lack it, so ship one."""
    import ctypes
    import os
    try:
        ctypes.CDLL("libfribidi.so.0")
    except OSError:
        bundled = os.path.join(os.path.dirname(__file__), "lib", "libfribidi.so.0")
        try:
            ctypes.CDLL(bundled, mode=ctypes.RTLD_GLOBAL)
        except OSError:
            pass


_preload_fribidi()
