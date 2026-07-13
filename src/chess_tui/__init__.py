"""Chess TUI package."""

__all__ = ["__version__", "greet"]

__version__ = "0.1.0"


def greet(name: str = "world") -> str:
    """Return a friendly greeting."""
    return f"Hello, {name}!"
