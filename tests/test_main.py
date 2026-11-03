"""Tests of the entry point of the visfem application."""

import errno
from types import SimpleNamespace

import pytest

from visfem import app as app_module
from visfem.app import VisfemApp


def test_visfem_app_importable() -> None:
    """Check that VisfemApp imports from visfem.app."""
    assert VisfemApp is not None


def _app_failing_with(err: OSError) -> type:
    """Return a stand-in for VisfemApp whose server raises *err* on start."""

    def start() -> None:
        raise err

    class FailingApp:
        """VisfemApp without a plotter, its server fails to start."""

        def __init__(self) -> None:
            self.server = SimpleNamespace(start=start)

    return FailingApp


def test_port_in_use_exits_with_a_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that a port in use ends visfem with a message naming it and --port, not a traceback."""
    bind_error = OSError(
        errno.EADDRINUSE,
        "error while attempting to bind on address ('127.0.0.1', 9000): address already in use",
    )
    monkeypatch.setattr(app_module, "VisfemApp", _app_failing_with(bind_error))
    with pytest.raises(SystemExit) as exc_info:
        app_module.main()
    message = str(exc_info.value.code)
    assert "('127.0.0.1', 9000): address already in use" in message
    assert "--port" in message


def test_other_os_errors_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that an OSError other than a port in use is not turned into the port message."""
    monkeypatch.setattr(
        app_module,
        "VisfemApp",
        _app_failing_with(OSError(errno.EACCES, "permission denied")),
    )
    with pytest.raises(PermissionError):
        app_module.main()
