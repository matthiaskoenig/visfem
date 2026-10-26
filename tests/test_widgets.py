"""Tests of the escaping of text for the Vue templates."""

import json

import pytest

from visfem.ui.widgets import js_string, js_text


@pytest.mark.parametrize(
    "value",
    [
        "heart",
        "f100-ResultsDataSet",
        "a'b\"c",
        "<img src=x onerror=alert(1)>",
        "{{ 7*7 }}",
        "back\\slash",
        "König 😀",
        "",
    ],
)
def test_js_string(value: str) -> None:
    """Check that the literal carries no markup or template syntax and decodes to value."""
    literal = js_string(value)
    assert literal[0] == literal[-1] == "'"
    body = literal[1:-1]
    # backslashes only start the escapes
    assert not set(body) & set("'\"<>{}&`")
    assert js_text(value) == "{{ " + literal + " }}"
    # the escapes are the \\uXXXX escapes of JSON
    assert json.loads(f'"{body}"') == value
