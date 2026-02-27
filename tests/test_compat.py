"""Tests for the httpxr.compat migration shim."""

from __future__ import annotations

import sys
import types
import warnings

import pytest

import httpxr
from httpxr import compat as compat_mod


@pytest.fixture(autouse=True)
def _isolate_compat() -> None:  # type: ignore[return]
    """Ensure each test starts with a clean module state."""
    # Disable shim if active
    if compat_mod.is_active():
        compat_mod.disable()

    # Save original httpx entry (real httpx is installed)
    original = sys.modules.get("httpx")

    # Save original submodule entries
    submodule_originals = {k: sys.modules.get(k) for k in compat_mod._SUBMODULE_ALIASES}

    # Remove httpx from sys.modules so each test starts clean
    sys.modules.pop("httpx", None)
    for k in compat_mod._SUBMODULE_ALIASES:
        sys.modules.pop(k, None)

    # Reset internal state
    compat_mod._shim_active = False
    compat_mod._original_httpx = None
    compat_mod._original_submodules.clear()

    yield  # type: ignore[misc]

    # Restore original state after test
    compat_mod._shim_active = False
    compat_mod._original_httpx = None
    compat_mod._original_submodules.clear()
    if original is not None:
        sys.modules["httpx"] = original
    else:
        sys.modules.pop("httpx", None)
    for k, v in submodule_originals.items():
        if v is not None:
            sys.modules[k] = v
        else:
            sys.modules.pop(k, None)


def _activate_shim() -> None:
    """Helper to activate the shim (since auto-activate on import
    only runs once)."""
    compat_mod._activate()


class TestCompatShim:
    """Tests for the httpx → httpxr shim."""

    def test_activate_enables_shim(self) -> None:
        """Activating the shim should register httpxr as httpx."""
        _activate_shim()

        assert compat_mod.is_active()
        assert "httpx" in sys.modules
        assert sys.modules["httpx"] is httpxr

    def test_httpx_resolves_to_httpxr(self) -> None:
        """After enabling the shim, import httpx returns httpxr."""
        _activate_shim()

        httpx = sys.modules["httpx"]
        assert httpx is httpxr

    def test_client_works_through_shim(self) -> None:
        """Client class should work when accessed via httpx."""
        _activate_shim()

        httpx = sys.modules["httpx"]
        assert httpx.Client is httpxr.Client  # type: ignore[union-attr]
        assert httpx.AsyncClient is httpxr.AsyncClient  # type: ignore[union-attr]

    def test_response_works_through_shim(self) -> None:
        """Response and other types should be accessible via httpx."""
        _activate_shim()

        httpx = sys.modules["httpx"]
        assert httpx.Response is httpxr.Response  # type: ignore[union-attr]
        assert httpx.Request is httpxr.Request  # type: ignore[union-attr]
        assert httpx.URL is httpxr.URL  # type: ignore[union-attr]

    def test_disable_removes_shim(self) -> None:
        """disable() should remove httpxr from sys.modules['httpx']."""
        _activate_shim()
        assert compat_mod.is_active()

        compat_mod.disable()
        assert not compat_mod.is_active()
        assert "httpx" not in sys.modules

    def test_disable_restores_original_httpx(self) -> None:
        """If httpx was previously imported, disable() restores it."""
        # Create a fake httpx module
        fake_httpx = types.ModuleType("httpx")
        fake_httpx.__version__ = "0.99.0"  # type: ignore[attr-defined]
        sys.modules["httpx"] = fake_httpx

        # Suppress the expected "already imported" warning — tested separately
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _activate_shim()
        assert compat_mod.is_active()
        assert sys.modules["httpx"] is httpxr

        # Disable should restore the fake
        compat_mod.disable()
        assert sys.modules["httpx"] is fake_httpx

    def test_warns_when_httpx_already_imported(self) -> None:
        """Shim should warn if httpx was already in sys.modules."""
        fake_httpx = types.ModuleType("httpx")
        sys.modules["httpx"] = fake_httpx

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _activate_shim()

        # Check that a warning was issued
        httpx_warnings = [x for x in w if "already imported" in str(x.message)]
        assert len(httpx_warnings) >= 1

    def test_is_active_reflects_state(self) -> None:
        """is_active() should reflect the current shim state."""
        assert not compat_mod.is_active()

        _activate_shim()
        assert compat_mod.is_active()

        compat_mod.disable()
        assert not compat_mod.is_active()

    def test_double_activate_is_safe(self) -> None:
        """Calling _activate() twice should be a no-op."""
        _activate_shim()
        assert compat_mod.is_active()

        # Second activation should not raise or change state
        _activate_shim()
        assert compat_mod.is_active()

    def test_double_disable_is_safe(self) -> None:
        """Calling disable() twice should be a no-op."""
        _activate_shim()
        compat_mod.disable()
        assert not compat_mod.is_active()

        # Second disable should not raise
        compat_mod.disable()
        assert not compat_mod.is_active()

    def test_exception_hierarchy_through_shim(self) -> None:
        """Exceptions should be accessible through the shim."""
        _activate_shim()

        httpx = sys.modules["httpx"]
        assert httpx.HTTPError is httpxr.HTTPError  # type: ignore[union-attr]
        assert httpx.RequestError is httpxr.RequestError  # type: ignore[union-attr]
        assert httpx.TimeoutException is httpxr.TimeoutException  # type: ignore[union-attr]

    def test_submodule_httpx_config_available(self) -> None:
        """httpx._config submodule provides DEFAULT_TIMEOUT_CONFIG."""
        _activate_shim()

        assert "httpx._config" in sys.modules
        config_mod = sys.modules["httpx._config"]
        assert hasattr(config_mod, "DEFAULT_TIMEOUT_CONFIG")
        assert isinstance(config_mod.DEFAULT_TIMEOUT_CONFIG, httpxr.Timeout)  # type: ignore[union-attr]

    def test_submodule_httpx_urls_available(self) -> None:
        """After enabling the shim, `from httpx._urls import URL` works."""
        _activate_shim()

        assert "httpx._urls" in sys.modules
        urls_mod = sys.modules["httpx._urls"]
        assert hasattr(urls_mod, "URL")
        assert urls_mod.URL is httpxr.URL  # type: ignore[union-attr]

    def test_submodule_cleanup_on_disable(self) -> None:
        """disable() should remove the submodule aliases."""
        _activate_shim()
        assert "httpx._config" in sys.modules

        compat_mod.disable()
        assert "httpx._config" not in sys.modules
        assert "httpx._urls" not in sys.modules

    def test_isinstance_check_works(self) -> None:
        """isinstance should work through the shim."""
        _activate_shim()

        httpx = sys.modules["httpx"]
        client = httpxr.Client(
            transport=httpxr.MockTransport(lambda r: httpxr.Response(200))
        )
        assert isinstance(client, httpx.Client)  # type: ignore[union-attr]
        client.close()
