from pydantic import BaseModel


class MyModel(BaseModel):
    pass


def print_something() -> str:
    """Simple function for printing."""
    message = "Hello, World!"
    print(message)
    return message


if __name__ == "__main__":
    print_something()
