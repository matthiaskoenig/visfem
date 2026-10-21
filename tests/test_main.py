"""Import smoke test for the visfem application class."""

from visfem.app import VisfemApp


def test_visfem_app_importable() -> None:
    """Check that VisfemApp imports from visfem.app."""
    assert VisfemApp is not None
