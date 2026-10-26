"""Logging setup: one RichHandler on the visfem logger, level from VISFEM_LOG_LEVEL, and the error text shown to the user."""

import logging
import os

from rich.logging import RichHandler

_ROOT = "visfem"


def _configure() -> logging.Logger:
    """Attach one RichHandler to the visfem logger at the level named by VISFEM_LOG_LEVEL (default WARNING); returns that logger."""
    root = logging.getLogger(_ROOT)
    if root.handlers:
        return root
    level = os.environ.get("VISFEM_LOG_LEVEL", "WARNING").upper()
    root.setLevel(logging.getLevelNamesMapping().get(level, logging.WARNING))
    handler = RichHandler(markup=False, rich_tracebacks=True, show_time=False)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    return root


def get_logger(name: str) -> logging.Logger:
    """Return the logger for name; records propagate to the visfem logger configured on first call."""
    _configure()
    return logging.getLogger(name)


def user_error(context: str, exc: BaseException) -> str:
    """Return the error text shown to the user: *context*, followed by the text of *exc* when VISFEM_SHOW_ERRORS is 1."""
    # The text of an exception can carry server paths; by default only the log gets it.
    if os.environ.get("VISFEM_SHOW_ERRORS", "0") == "1":
        return f"{context}: {exc}"
    return context
