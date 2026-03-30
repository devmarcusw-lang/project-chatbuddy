"""Compatibility entrypoint for ChatBuddy."""

from chatbuddy.main import main
from chatbuddy.runtime import bot

__all__ = ["bot", "main"]


if __name__ == "__main__":
    main()
