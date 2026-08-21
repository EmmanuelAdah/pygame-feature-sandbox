# Rock • Paper • Scissors

A polished, animated Rock-Paper-Scissors arcade game built with **Python** and
**Pygame** — dramatic computer "thinking" animation, synthesized sound
effects and music, particle effects, a full menu system, and best-of-N
match play against the computer.

## Features

- Classic Rock-Paper-Scissors gameplay with correct win/lose/draw rules
- Computer AI with a dramatic reveal: a "3, 2, 1" countdown followed by a
  rapid icon-cycling animation before its choice locks in
- Best-of-N match modes: **First to 3 / 5 / 10**
- Animated everything: springy button hovers, a scale-in reveal, a
  glowing/pulsing winner and a shrinking loser, popping score numbers,
  and a confetti-style particle burst on every win/loss/draw
- Full sound design — **every effect and the background music are
  synthesized procedurally at startup**, so the game runs with zero
  external audio files, and will automatically use real `.wav`/`.ogg`
  files instead if you drop them into `assets/`
- Stylized, shaded artwork (shadows, gradients, highlights) for the rock,
  paper and scissors pieces, also procedurally generated and also
  overridable with real PNGs
- Main menu, How-to-Play screen, Settings (music/SFX toggle + volume
  slider), pause menu, and a match-over screen with Play Again / Main Menu
- Fullscreen toggle and freely resizable window — the game renders to a
  fixed internal resolution and cleanly letterboxes/scales to whatever
  window size you use
- Keyboard shortcuts for everything, in addition to full mouse support
- Graceful handling of missing/corrupt asset files (falls back to
  generated art/sound and prints a warning instead of crashing)

## Installation

```bash
git clone <repository>
cd rock_paper_scissors
pip install -r requirements.txt
```

## Running

```bash
python main.py
```

## Controls

```text
Mouse        - Navigate menus, click Rock / Paper / Scissors
R            - Choose Rock
P            - Choose Paper
S            - Choose Scissors
ESC          - Pause / Resume / Back
M            - Toggle background music
F11          - Toggle fullscreen
```

## Using real artwork or audio instead of the generated placeholders

Every asset is loaded through a "real file first, generated fallback
second" system. To upgrade the visuals or audio, just drop correctly named
files into these folders — no code changes needed:

```text
assets/
├── images/
│   ├── rock.png          (any size; scaled automatically, keeps aspect ratio)
│   ├── paper.png
│   ├── scissors.png
│   ├── background.png    (ideally 1280x720)
│   └── logo.png
├── sounds/
│   ├── button_hover.wav
│   ├── button_click.wav
│   ├── countdown.wav
│   ├── reveal.wav
│   ├── player_win.wav
│   ├── computer_win.wav
│   ├── draw.wav
│   ├── round_start.wav
│   ├── match_win.wav
│   └── match_loss.wav
└── music/
    └── background.ogg    (.mp3 / .wav also work)
```

If a file is missing, unreadable, or corrupt, the game prints a warning to
the console and continues on with a procedurally generated replacement —
it will never crash because of a missing asset.

## Project structure

```text
rock_paper_scissors/
├── main.py                # Entry point
├── requirements.txt
├── README.md
├── assets/
│   ├── images/            # Drop real PNGs here to override generated art
│   ├── sounds/             # Drop real WAV/OGG/MP3 here to override synthesized SFX
│   └── music/
└── src/
    ├── settings.py         # All configuration/constants in one place
    ├── assets.py           # AssetManager - loads or procedurally generates images
    ├── sound.py             # SoundManager - loads or synthesizes every sound
    ├── ui.py                 # Button / ToggleButton / Slider widgets
    ├── animations.py          # Tween + particle system
    ├── utils.py                # Easing functions, scaling, text/gradient helpers
    └── game.py                  # Game state machine, round logic, all screens
```

### Architecture notes

- **State machine, not a monolithic loop.** `Game` holds a `GameState`
  (`MENU`, `HOW_TO_PLAY`, `SETTINGS`, `MODE_SELECT`, `PLAYING`, `PAUSED`,
  `MATCH_OVER`) and dispatches to small per-screen update/draw methods.
  Gameplay itself is a nested state machine of `RoundPhase` values
  (`CHOOSING → COUNTDOWN → CYCLING → REVEAL → RESULT`).
- **Pause-safe timing.** Round-phase animation timers run off a custom
  `game_time_ms` clock that only advances while the state is `PLAYING`,
  not off the OS wall clock — so pausing mid-round and resuming later
  never causes the round to "jump ahead."
- **Fixed internal resolution.** Everything is drawn to a 1280×720
  surface, which is then scaled and letterboxed to the real window each
  frame. This means fullscreen and window-resizing work correctly with no
  per-element layout recalculation, and mouse clicks are translated back
  into internal-canvas coordinates automatically.
- **`determine_winner(player, computer)`** is a small pure function
  (in `game.py`) that returns `"player"`, `"computer"`, or `"draw"` — kept
  separate from all UI/animation code so the rules are easy to verify.
