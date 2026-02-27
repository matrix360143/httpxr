"""
httpxr.compat — drop-in migration shim for httpx.

Import once at your application's entrypoint to redirect all ``import httpx``
statements to httpxr (including third-party libraries)::

    import httpxr.compat   # enable the shim
    import httpx            # ← now resolves to httpxr

    httpxr.compat.is_active()  # True
    httpxr.compat.disable()    # restore original httpx
"""

from __future__ import annotations

import logging
import sys
import types
import warnings

import httpxr

logger = logging.getLogger("httpxr.compat")

_original_httpx: types.ModuleType | None = None
_original_submodules: dict[str, types.ModuleType | None] = {}
_shim_active: bool = False

# Submodule paths that the openai SDK (and others) import internally.
_SUBMODULE_ALIASES: dict[str, dict[str, str]] = {
    "httpx._config": {
        "DEFAULT_TIMEOUT_CONFIG": "DEFAULT_TIMEOUT_CONFIG",
    },
    "httpx._urls": {
        "URL": "URL",
        "QueryParams": "QueryParams",
    },
    "httpx._types": {
        "Headers": "Headers",
        "QueryParams": "QueryParams",
    },
    "httpx._content": {},
}


def _make_submodule(name: str, attrs: dict[str, str]) -> types.ModuleType:
    """Create a lightweight module that proxies attributes from httpxr."""
    mod = types.ModuleType(name)
    mod.__package__ = "httpx"
    for attr_name, httpxr_attr in attrs.items():
        setattr(mod, attr_name, getattr(httpxr, httpxr_attr))
    return mod


def _activate() -> None:
    global _original_httpx, _shim_active

    if _shim_active:
        return

    if "httpx" in sys.modules:
        _original_httpx = sys.modules["httpx"]
        warnings.warn(
            "httpxr.compat: 'httpx' was already imported. "
            "The shim will override it, but modules that already hold "
            "a reference to the original httpx objects will not be affected.",
            stacklevel=3,
        )

    sys.modules["httpx"] = httpxr  # type: ignore[assignment]

    # Register internal submodule aliases so that
    # `from httpx._config import DEFAULT_TIMEOUT_CONFIG` works.
    for sub_path, attrs in _SUBMODULE_ALIASES.items():
        _original_submodules[sub_path] = sys.modules.get(sub_path)
        sys.modules[sub_path] = _make_submodule(sub_path, attrs)

    _shim_active = True
    logger.info("httpxr.compat: httpx → httpxr shim active")


def disable() -> None:
    """Disable the shim and restore the original ``httpx`` module (if any)."""
    global _original_httpx, _shim_active

    if not _shim_active:
        return

    if _original_httpx is not None:
        sys.modules["httpx"] = _original_httpx
        _original_httpx = None
    else:
        sys.modules.pop("httpx", None)

    # Restore or remove submodule aliases.
    for sub_path in _SUBMODULE_ALIASES:
        orig = _original_submodules.pop(sub_path, None)
        if orig is not None:
            sys.modules[sub_path] = orig
        else:
            sys.modules.pop(sub_path, None)

    _shim_active = False
    logger.info("httpxr.compat: shim disabled")


def is_active() -> bool:
    """Return ``True`` if the httpx → httpxr shim is currently active."""
    return _shim_active


_activate()
