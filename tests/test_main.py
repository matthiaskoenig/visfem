from visfem.main import print_something


def test_print_something() -> None:
    assert print_something() == "Hello, World!"
