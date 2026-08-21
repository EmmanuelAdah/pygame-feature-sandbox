#!/usr/bin/env python3
"""
Rock • Paper • Scissors
========================
Entry point. Run with:

    python main.py
"""

from src.game import Game


def main() -> None:
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
