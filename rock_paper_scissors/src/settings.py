"""
Central configuration for Rock • Paper • Scissors.

Keeping every tunable value in one place makes the game easy to re-theme
or re-balance without hunting through gameplay code.
"""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path

# --------------------------------------------------------------------------
# Paths (pathlib -> portable across Windows / macOS / Linux)
# --------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
IMAGES_DIR = ASSETS_DIR / "images"
SOUNDS_DIR = ASSETS_DIR / "sounds"
MUSIC_DIR = ASSETS_DIR / "music"

# --------------------------------------------------------------------------
# Window / performance
# --------------------------------------------------------------------------

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
TITLE = "Rock • Paper • Scissors"

# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------

MUSIC_VOLUME = 0.35
SFX_VOLUME = 0.75

# --------------------------------------------------------------------------
# Palette - modern dark arcade theme
# --------------------------------------------------------------------------

COLOR_BG_TOP = (16, 19, 30)
COLOR_BG_BOTTOM = (8, 9, 16)
COLOR_PANEL = (26, 30, 44)
COLOR_PANEL_LIGHT = (38, 43, 62)
COLOR_TEXT = (235, 238, 245)
COLOR_SUBTEXT = (150, 158, 178)
COLOR_ACCENT = (90, 200, 255)
COLOR_GOLD = (255, 200, 80)
COLOR_WIN = (100, 230, 150)
COLOR_LOSS = (240, 95, 105)
COLOR_DRAW = (175, 180, 200)
COLOR_BUTTON = (48, 53, 74)
COLOR_BUTTON_HOVER = (72, 80, 108)

# --------------------------------------------------------------------------
# Game rules
# --------------------------------------------------------------------------


class Choice(Enum):
    ROCK = "rock"
    PAPER = "paper"
    SCISSORS = "scissors"

    @property
    def label(self) -> str:
        return self.value.upper()


CHOICES: list[Choice] = [Choice.ROCK, Choice.PAPER, Choice.SCISSORS]

# BEATS[x] is the choice that `x` defeats.
BEATS: dict[Choice, Choice] = {
    Choice.ROCK: Choice.SCISSORS,
    Choice.SCISSORS: Choice.PAPER,
    Choice.PAPER: Choice.ROCK,
}

MATCH_TARGETS: list[int] = [3, 5, 10]
DEFAULT_MATCH_TARGET = 3


# --------------------------------------------------------------------------
# State machine
# --------------------------------------------------------------------------


class GameState(Enum):
    MENU = auto()
    HOW_TO_PLAY = auto()
    SETTINGS = auto()
    MODE_SELECT = auto()
    PLAYING = auto()
    PAUSED = auto()
    MATCH_OVER = auto()
    QUIT = auto()


class RoundPhase(Enum):
    CHOOSING = auto()
    COUNTDOWN = auto()
    CYCLING = auto()
    REVEAL = auto()
    RESULT = auto()


# --------------------------------------------------------------------------
# Animation timings (milliseconds unless noted)
# --------------------------------------------------------------------------

COUNTDOWN_STEP_MS = 450          # time per "3", "2", "1" tick
CYCLING_DURATION_MS = 900        # how long the computer's icon rapid-cycles
CYCLING_STEP_MS = 80             # speed of the rapid-cycle flicker
REVEAL_DURATION_MS = 400         # scale-in + approach animation
RESULT_HOLD_MS = 1800            # how long the result is shown before advancing
SCORE_POP_MS = 350
BUTTON_HOVER_LERP = 12.0         # per-second lerp speed for hover scale
