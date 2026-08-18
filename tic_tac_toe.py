"""
TIC-TAC-TOE (with synthesized sound effects + juicy animations)
=================================================================
A classic 3x3 Tic-Tac-Toe game built with Pygame. All sound effects are
generated procedurally at startup (no external audio files or internet
required) using simple waveform synthesis, so the game runs out of the box.

On top of the core game, this version adds "juice" to make it feel alive:
    - Marks pop into place with a springy scale animation
    - Hovering an empty cell shows a soft ghost preview of your mark
    - Invalid clicks shake the board and flash the offending cell red
    - The winning line animates as it draws itself
    - A confetti burst celebrates a win
    - The status text pops when it changes ("X's Turn" -> "O's Turn" etc.)
    - The restart button has hover/press spring animations

Requires:
    pip install pygame numpy

Run:
    python tic_tac_toe.py

Controls:
    Mouse click -> place a mark / press buttons
    R           -> restart at any time
    ESC / Q     -> quit
"""

import sys
import math
import random
import numpy as np
import pygame

# --------------------------------------------------------------------------
# CONFIGURATION / CONSTANTS
# --------------------------------------------------------------------------

WINDOW_WIDTH = 620
WINDOW_HEIGHT = 700          # kept compact so the restart button is always
                              # visible, even on smaller/laptop screens
FPS = 60

BOARD_SIZE = 460             # square board pixel size
BOARD_MARGIN_TOP = 130       # space reserved for header/status
CELL_SIZE = BOARD_SIZE // 3
GRID_LINE_WIDTH = 6
MARK_LINE_WIDTH = 14
MARK_PADDING = 30            # inset for drawing X/O within a cell

SAMPLE_RATE = 44100

# Colors - minimalist high-contrast neon-on-dark theme
COLOR_BG = (18, 20, 28)
COLOR_GRID = (90, 96, 120)
COLOR_X = (0, 220, 210)      # cyan
COLOR_O = (255, 100, 140)    # pink
COLOR_TEXT = (235, 235, 240)
COLOR_SUBTEXT = (150, 155, 170)
COLOR_WIN_LINE = (255, 215, 90)
COLOR_BUTTON = (55, 60, 80)
COLOR_BUTTON_HOVER = (80, 88, 118)
COLOR_BUTTON_TEXT = (240, 240, 245)
COLOR_CELL_HOVER = (32, 35, 50)
COLOR_INVALID_FLASH = (200, 70, 70)

CONFETTI_COLORS = [
    (0, 220, 210), (255, 100, 140), (255, 215, 90),
    (140, 160, 255), (255, 255, 255),
]

WIN_COMBINATIONS = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),   # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),   # columns
    (0, 4, 8), (2, 4, 6),              # diagonals
]

# Animation durations (milliseconds)
MARK_POP_DURATION = 260
STATUS_POP_DURATION = 240
WIN_LINE_DURATION = 350
SHAKE_DURATION = 260
INVALID_FLASH_DURATION = 260
CONFETTI_LIFETIME = 1400

FONT_LARGE = None
FONT_MEDIUM = None
FONT_SMALL = None


# --------------------------------------------------------------------------
# EASING HELPERS
# --------------------------------------------------------------------------

def clamp01(t):
    return max(0.0, min(1.0, t))


def ease_out_cubic(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def ease_out_back(t, overshoot=1.7):
    """Overshoots past 1.0 then settles - gives a springy 'pop' feel."""
    t = clamp01(t)
    t -= 1
    return 1 + (overshoot + 1) * (t ** 3) + overshoot * (t ** 2)


# ==========================================================================
# AUDIO MANAGER
# --------------------------------------------------------------------------
# Handles all sound synthesis and playback, fully decoupled from game logic
# and rendering. Sounds are generated once at startup using basic waveform
# synthesis (sine/square waves with envelopes) and cached as pygame Sound
# objects.
# ==========================================================================

class AudioManager:
    def __init__(self, sample_rate=SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.enabled = True
        self.sounds = {}

        try:
            pygame.mixer.init(frequency=sample_rate, size=-16, channels=1)
            self._build_sounds()
        except pygame.error:
            # No audio device available - fail gracefully, game still playable
            self.enabled = False

    # ---- low-level waveform helpers ------------------------------------

    def _envelope(self, n_samples, attack=0.02, release=0.4):
        """Simple linear attack/decay envelope to avoid audio clicks/pops."""
        env = np.ones(n_samples)
        attack_n = max(1, int(n_samples * attack))
        release_n = max(1, int(n_samples * release))
        env[:attack_n] = np.linspace(0, 1, attack_n)
        env[-release_n:] *= np.linspace(1, 0, release_n)
        return env

    def _tone(self, freq, duration, volume=0.5, waveform="sine",
              attack=0.02, release=0.5):
        n_samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, n_samples, endpoint=False)

        if waveform == "sine":
            wave = np.sin(2 * np.pi * freq * t)
        elif waveform == "square":
            wave = np.sign(np.sin(2 * np.pi * freq * t))
        elif waveform == "triangle":
            wave = 2 * np.abs(2 * (t * freq - np.floor(t * freq + 0.5))) - 1
        else:
            wave = np.sin(2 * np.pi * freq * t)

        wave *= self._envelope(n_samples, attack, release)
        wave *= volume
        return wave

    def _noise_burst(self, duration, volume=0.3, low_pass_alpha=0.15):
        """Filtered white noise, used for the 'thud' error sound."""
        n_samples = int(self.sample_rate * duration)
        raw = np.random.uniform(-1, 1, n_samples)
        # crude low-pass filter (exponential moving average) for a "thud"
        filtered = np.zeros(n_samples)
        acc = 0.0
        for i in range(n_samples):
            acc = low_pass_alpha * raw[i] + (1 - low_pass_alpha) * acc
            filtered[i] = acc
        filtered *= self._envelope(n_samples, attack=0.01, release=0.6)
        filtered *= volume
        return filtered

    def _to_sound(self, wave):
        wave = np.clip(wave, -1, 1)
        mono = (wave * 32767).astype(np.int16)
        # Always build a 2-channel (stereo) buffer - some platforms/mixer
        # configs report as stereo even when initialized with channels=1,
        # so duplicating the mono signal into both channels keeps this
        # robust across environments.
        stereo = np.column_stack((mono, mono))
        return pygame.sndarray.make_sound(np.ascontiguousarray(stereo))

    def _concat(self, *waves):
        return np.concatenate(waves)

    # ---- sound construction ---------------------------------------------

    def _build_sounds(self):
        # 1) Mark placement: short crisp "pop" - quick high sine blip
        pop_duration = 0.08
        pop = self._tone(880, pop_duration, volume=0.5, waveform="sine",
                          attack=0.01, release=0.6)
        overtone = self._tone(1320, pop_duration, volume=0.2, waveform="sine",
                               attack=0.01, release=0.7)
        pop += overtone  # same duration -> same sample count, safe to add
        self.sounds["place"] = self._to_sound(pop)

        # 2) Invalid move: muted low "thud" / buzz
        thud = self._noise_burst(0.15, volume=0.35, low_pass_alpha=0.08)
        buzz = self._tone(120, 0.15, volume=0.25, waveform="square",
                           attack=0.01, release=0.8)
        self.sounds["invalid"] = self._to_sound(thud * 0.7 + buzz * 0.5)

        # 3) Win condition: cheerful ascending fanfare (arpeggio)
        notes = [523.25, 659.25, 783.99, 1046.50]  # C5 E5 G5 C6
        fanfare_parts = [
            self._tone(f, 0.14, volume=0.45, waveform="triangle",
                       attack=0.01, release=0.5)
            for f in notes
        ]
        self.sounds["win"] = self._to_sound(self._concat(*fanfare_parts))

        # 4) Draw condition: neutral descending tone
        draw_notes = [440.0, 349.23, 293.66]  # A4 -> F4 -> D4
        draw_parts = [
            self._tone(f, 0.2, volume=0.35, waveform="sine",
                       attack=0.02, release=0.6)
            for f in draw_notes
        ]
        self.sounds["draw"] = self._to_sound(self._concat(*draw_parts))

        # 5) Restart: quick swoosh (frequency sweep / chirp)
        duration = 0.35
        n_samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, n_samples, endpoint=False)
        start_freq, end_freq = 1400, 300
        freq_sweep = np.linspace(start_freq, end_freq, n_samples)
        phase = np.cumsum(2 * np.pi * freq_sweep / self.sample_rate)
        swoosh = np.sin(phase) * self._envelope(n_samples, attack=0.05, release=0.7)
        swoosh *= 0.35
        self.sounds["restart"] = self._to_sound(swoosh)

        # 6) Hover tick: tiny, subtle blip when the mouse enters a new cell
        hover = self._tone(1600, 0.03, volume=0.12, waveform="sine",
                            attack=0.01, release=0.8)
        self.sounds["hover"] = self._to_sound(hover)

    # ---- public API -------------------------------------------------------

    def play(self, name):
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if sound is not None:
            sound.play()


# ==========================================================================
# GAME LOGIC
# --------------------------------------------------------------------------
# Pure game-state logic, decoupled from rendering and audio. The UI layer
# calls into this class and reacts to its return values / state. Timestamps
# are recorded here (rather than free-floating in the UI layer) so that
# resetting the game also cleanly resets all animation state.
# ==========================================================================

class TicTacToeGame:
    def __init__(self, audio: AudioManager):
        self.audio = audio
        self.reset()

    def reset(self):
        self.board = [None] * 9          # None, "X", or "O" per cell
        self.current_player = "X"
        self.winner = None               # "X", "O", or "DRAW"
        self.winning_combo = None        # tuple of 3 indices, if a win occurred
        self.game_over = False

        now = pygame.time.get_ticks()
        self.mark_times = [None] * 9     # timestamp each cell's mark was placed
        self.win_time = None             # timestamp a win was detected
        self.status_change_time = now    # timestamp status text last changed
        self.invalid_index = None        # last cell clicked while occupied
        self.invalid_time = 0            # timestamp of that invalid click
        self.confetti_spawned = False    # guards against re-spawning confetti

    def attempt_move(self, index):
        """
        Try to place the current player's mark at `index` (0-8).
        Plays the appropriate sound and updates game state (including
        timestamps used to drive animations).
        Returns True if the move was accepted, False if invalid/rejected.
        """
        if self.game_over:
            return False

        now = pygame.time.get_ticks()

        if self.board[index] is not None:
            self.audio.play("invalid")
            self.invalid_index = index
            self.invalid_time = now
            return False

        self.board[index] = self.current_player
        self.mark_times[index] = now
        self.audio.play("place")

        combo = self._check_winner(self.current_player)
        if combo:
            self.winner = self.current_player
            self.winning_combo = combo
            self.game_over = True
            self.win_time = now
            self.audio.play("win")
        elif all(cell is not None for cell in self.board):
            self.winner = "DRAW"
            self.game_over = True
            self.audio.play("draw")
        else:
            self.current_player = "O" if self.current_player == "X" else "X"

        self.status_change_time = now
        return True

    def _check_winner(self, player):
        """Return the winning combination tuple if `player` has won, else None."""
        for combo in WIN_COMBINATIONS:
            a, b, c = combo
            if self.board[a] == self.board[b] == self.board[c] == player:
                return combo
        return None

    def status_text(self):
        if self.winner == "DRAW":
            return "It's a Draw!"
        if self.winner in ("X", "O"):
            return f"Player {self.winner} Wins!"
        return f"Player {self.current_player}'s Turn"


# ==========================================================================
# PARTICLES (confetti burst on win)
# ==========================================================================

class Particle:
    __slots__ = ("x", "y", "vx", "vy", "color", "size", "born", "rotation", "spin")

    def __init__(self, x, y, now):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(2.5, 7.5)
        self.x = x
        self.y = y
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - 3.5  # initial upward pop
        self.color = random.choice(CONFETTI_COLORS)
        self.size = random.uniform(4, 8)
        self.born = now
        self.rotation = random.uniform(0, 360)
        self.spin = random.uniform(-6, 6)

    def update(self):
        self.vy += 0.22  # gravity
        self.x += self.vx
        self.y += self.vy
        self.rotation += self.spin

    def age_ratio(self, now):
        return clamp01((now - self.born) / CONFETTI_LIFETIME)

    def alive(self, now):
        return (now - self.born) < CONFETTI_LIFETIME

    def draw(self, surface, now):
        alpha = int(255 * (1 - self.age_ratio(now)))
        if alpha <= 0:
            return
        s = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, self.size, self.size * 1.6)
        rect.center = (self.size, self.size)
        pygame.draw.rect(s, (*self.color, alpha), rect, border_radius=2)
        rotated = pygame.transform.rotate(s, self.rotation)
        r = rotated.get_rect(center=(self.x, self.y))
        surface.blit(rotated, r)


def spawn_confetti(cx, cy, now, count=90):
    return [Particle(cx, cy, now) for _ in range(count)]


# ==========================================================================
# RENDERING
# ==========================================================================

def cell_rect(index, offset=(0, 0)):
    row, col = divmod(index, 3)
    x = (WINDOW_WIDTH - BOARD_SIZE) // 2 + col * CELL_SIZE + offset[0]
    y = BOARD_MARGIN_TOP + row * CELL_SIZE + offset[1]
    return pygame.Rect(x, y, CELL_SIZE, CELL_SIZE)


def board_rect_with_offset(offset):
    board_left = (WINDOW_WIDTH - BOARD_SIZE) // 2 + offset[0]
    board_top = BOARD_MARGIN_TOP + offset[1]
    return pygame.Rect(board_left, board_top, BOARD_SIZE, BOARD_SIZE)


def get_shake_offset(game: TicTacToeGame, now):
    """A brief decaying horizontal shake, triggered by an invalid click."""
    if game.invalid_index is None:
        return (0, 0)
    elapsed = now - game.invalid_time
    if elapsed >= SHAKE_DURATION:
        return (0, 0)
    t = elapsed / SHAKE_DURATION
    decay = 1 - t
    offset_x = math.sin(t * math.pi * 6) * 6 * decay
    return (offset_x, 0)


def draw_grid(surface, offset):
    board_rect = board_rect_with_offset(offset)
    board_left, board_top = board_rect.left, board_rect.top

    pygame.draw.rect(surface, (26, 28, 38), board_rect, border_radius=14)

    for i in (1, 2):
        x = board_left + i * CELL_SIZE
        pygame.draw.line(surface, COLOR_GRID, (x, board_top + 10),
                          (x, board_top + BOARD_SIZE - 10), GRID_LINE_WIDTH)
        y = board_top + i * CELL_SIZE
        pygame.draw.line(surface, COLOR_GRID, (board_left + 10, y),
                          (board_left + BOARD_SIZE - 10, y), GRID_LINE_WIDTH)


def draw_mark(surface, mark, rect, color, alpha=255, scale=1.0):
    """Draws an X or O, scaled from its cell's center (used for pop-in and
    the low-alpha hover preview)."""
    half = (CELL_SIZE - MARK_PADDING * 2) // 2
    half = max(2, int(half * scale))
    line_width = max(2, int(MARK_LINE_WIDTH * scale))

    mark_surf = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
    local_center = (CELL_SIZE // 2, CELL_SIZE // 2)

    if mark == "X":
        pygame.draw.line(
            mark_surf, (*color, alpha),
            (local_center[0] - half, local_center[1] - half),
            (local_center[0] + half, local_center[1] + half),
            line_width,
        )
        pygame.draw.line(
            mark_surf, (*color, alpha),
            (local_center[0] + half, local_center[1] - half),
            (local_center[0] - half, local_center[1] + half),
            line_width,
        )
    elif mark == "O":
        pygame.draw.circle(mark_surf, (*color, alpha), local_center, half, line_width)

    surface.blit(mark_surf, rect.topleft)


def draw_board(surface, game: TicTacToeGame, hovered_index, now, offset):
    draw_grid(surface, offset)

    for i, mark in enumerate(game.board):
        rect = cell_rect(i, offset)

        is_winning_cell = game.winning_combo and i in game.winning_combo
        is_invalid_flash = (
            game.invalid_index == i and (now - game.invalid_time) < INVALID_FLASH_DURATION
        )

        if is_invalid_flash:
            t = (now - game.invalid_time) / INVALID_FLASH_DURATION
            alpha = int(140 * (1 - t))
            flash_rect = rect.inflate(-14, -14)
            flash_surf = pygame.Surface(flash_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(flash_surf, (*COLOR_INVALID_FLASH, alpha),
                              flash_surf.get_rect(), border_radius=10)
            surface.blit(flash_surf, flash_rect.topleft)
        elif is_winning_cell:
            pulse = 0.5 + 0.5 * math.sin(now / 180.0)
            glow_alpha = int(50 + 40 * pulse)
            highlight_rect = rect.inflate(-14, -14)
            highlight_surf = pygame.Surface(highlight_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(highlight_surf, (255, 215, 90, glow_alpha),
                              highlight_surf.get_rect(), border_radius=10)
            surface.blit(highlight_surf, highlight_rect.topleft)
        elif (not game.game_over) and mark is None and hovered_index == i:
            hover_rect = rect.inflate(-14, -14)
            pygame.draw.rect(surface, COLOR_CELL_HOVER, hover_rect, border_radius=10)

        if mark is not None:
            color = COLOR_X if mark == "X" else COLOR_O
            placed_at = game.mark_times[i]
            if placed_at is not None:
                elapsed = now - placed_at
                if elapsed < MARK_POP_DURATION:
                    scale = ease_out_back(elapsed / MARK_POP_DURATION)
                    scale = max(0.0, scale)
                else:
                    scale = 1.0
            else:
                scale = 1.0
            draw_mark(surface, mark, rect, color, alpha=255, scale=scale)
        elif (not game.game_over) and hovered_index == i:
            # Ghost preview of the current player's mark on hover
            ghost_color = COLOR_X if game.current_player == "X" else COLOR_O
            draw_mark(surface, game.current_player, rect, ghost_color, alpha=70, scale=1.0)

    # Animated winning line: grows outward from the center of the combo
    if game.winning_combo and game.win_time is not None:
        a, mid, c = game.winning_combo
        start_rect = cell_rect(a, offset)
        end_rect = cell_rect(c, offset)
        mid_point = cell_rect(mid, offset).center

        t = ease_out_cubic((now - game.win_time) / WIN_LINE_DURATION)
        sx = mid_point[0] + (start_rect.centerx - mid_point[0]) * t
        sy = mid_point[1] + (start_rect.centery - mid_point[1]) * t
        ex = mid_point[0] + (end_rect.centerx - mid_point[0]) * t
        ey = mid_point[1] + (end_rect.centery - mid_point[1]) * t

        pygame.draw.line(surface, COLOR_WIN_LINE, (sx, sy), (ex, ey), 10)
        pygame.draw.circle(surface, COLOR_WIN_LINE, (int(sx), int(sy)), 6)
        pygame.draw.circle(surface, COLOR_WIN_LINE, (int(ex), int(ey)), 6)


def draw_header(surface, game: TicTacToeGame, now):
    # Gentle color pulse on the title for a bit of ambient life
    pulse = 0.5 + 0.5 * math.sin(now / 700.0)
    title_color = (
        int(COLOR_TEXT[0]),
        int(COLOR_TEXT[1] - 20 * pulse),
        int(COLOR_TEXT[2]),
    )
    title = FONT_LARGE.render("TIC-TAC-TOE", True, title_color)
    title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, 42))
    surface.blit(title, title_rect)

    status_color = COLOR_TEXT
    if game.winner == "X":
        status_color = COLOR_X
    elif game.winner == "O":
        status_color = COLOR_O
    elif game.winner == "DRAW":
        status_color = COLOR_SUBTEXT

    # Status text "pops" briefly whenever it changes
    elapsed = now - game.status_change_time
    if elapsed < STATUS_POP_DURATION:
        scale = 1.0 + 0.28 * (1 - ease_out_cubic(elapsed / STATUS_POP_DURATION))
    else:
        scale = 1.0

    status_surf = FONT_MEDIUM.render(game.status_text(), True, status_color)
    if scale != 1.0:
        w, h = status_surf.get_size()
        status_surf = pygame.transform.smoothscale(
            status_surf, (max(1, int(w * scale)), max(1, int(h * scale)))
        )
    status_rect = status_surf.get_rect(center=(WINDOW_WIDTH // 2, 92))
    surface.blit(status_surf, status_rect)

    # Pulsing turn indicator dot (hidden once the game is over)
    if not game.game_over:
        dot_color = COLOR_X if game.current_player == "X" else COLOR_O
        dot_pulse = 0.5 + 0.5 * math.sin(now / 220.0)
        radius = 5 + int(3 * dot_pulse)
        dot_x = status_rect.left - 22
        dot_y = status_rect.centery
        glow_surf = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*dot_color, 70), (radius * 2, radius * 2), radius * 2)
        surface.blit(glow_surf, (dot_x - radius * 2, dot_y - radius * 2))
        pygame.draw.circle(surface, dot_color, (dot_x, dot_y), radius)


def draw_restart_button(surface, base_rect, mouse_pos, button_scale, is_pressed):
    hovered = base_rect.collidepoint(mouse_pos)
    color = COLOR_BUTTON_HOVER if hovered else COLOR_BUTTON

    scaled_w = int(base_rect.width * button_scale)
    scaled_h = int(base_rect.height * button_scale)
    rect = pygame.Rect(0, 0, scaled_w, scaled_h)
    rect.center = base_rect.center

    shadow_rect = rect.move(0, 4)
    pygame.draw.rect(surface, (10, 11, 16), shadow_rect, border_radius=12)

    pygame.draw.rect(surface, color, rect, border_radius=12)
    border_color = COLOR_WIN_LINE if hovered else COLOR_GRID
    pygame.draw.rect(surface, border_color, rect, width=2, border_radius=12)

    # Small refresh/restart icon (two curved arrows drawn as arcs)
    icon_cx = rect.centerx - 58
    icon_cy = rect.centery
    icon_r = 9
    arc_rect = pygame.Rect(icon_cx - icon_r, icon_cy - icon_r, icon_r * 2, icon_r * 2)
    pygame.draw.arc(surface, COLOR_BUTTON_TEXT, arc_rect, 0.6, 5.4, 3)
    tip = (icon_cx + icon_r - 1, icon_cy - 6)
    pygame.draw.polygon(surface, COLOR_BUTTON_TEXT, [
        (tip[0] - 6, tip[1] - 2), (tip[0] + 2, tip[1] + 2), (tip[0] - 3, tip[1] + 6)
    ])

    label = FONT_MEDIUM.render("Play Again", True, COLOR_BUTTON_TEXT)
    label_rect = label.get_rect(center=(rect.centerx + 12, rect.centery))
    surface.blit(label, label_rect)


def draw_footer_hint(surface):
    hint = FONT_SMALL.render("Press R to restart  -  ESC to quit", True, COLOR_SUBTEXT)
    hint_rect = hint.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT - 18))
    surface.blit(hint, hint_rect)


def draw_all(surface, game: TicTacToeGame, hovered_index, restart_base_rect,
             mouse_pos, now, particles, button_scale, is_pressed):
    surface.fill(COLOR_BG)

    shake_offset = get_shake_offset(game, now)

    draw_header(surface, game, now)
    draw_board(surface, game, hovered_index, now, shake_offset)

    for p in particles:
        p.draw(surface, now)

    draw_restart_button(surface, restart_base_rect, mouse_pos, button_scale, is_pressed)
    draw_footer_hint(surface)


# ==========================================================================
# INPUT HANDLING
# ==========================================================================

def get_hovered_cell(mouse_pos):
    board_left = (WINDOW_WIDTH - BOARD_SIZE) // 2
    board_top = BOARD_MARGIN_TOP
    board_rect = pygame.Rect(board_left, board_top, BOARD_SIZE, BOARD_SIZE)

    if not board_rect.collidepoint(mouse_pos):
        return None

    col = (mouse_pos[0] - board_left) // CELL_SIZE
    row = (mouse_pos[1] - board_top) // CELL_SIZE
    index = row * 3 + col
    if 0 <= index < 9:
        return index
    return None


def handle_events(game: TicTacToeGame, audio: AudioManager, restart_rect, ui_state):
    """Process discrete input events. Returns False if the app should quit."""
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                return False
            if event.key == pygame.K_r:
                audio.play("restart")
                game.reset()
                ui_state["particles"] = []

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = event.pos

            if restart_rect.collidepoint(mouse_pos):
                audio.play("restart")
                game.reset()
                ui_state["particles"] = []
                ui_state["button_press_time"] = pygame.time.get_ticks()
                continue

            index = get_hovered_cell(mouse_pos)
            if index is not None:
                game.attempt_move(index)

    return True


# ==========================================================================
# MAIN ENTRY POINT
# ==========================================================================

def main():
    global FONT_LARGE, FONT_MEDIUM, FONT_SMALL

    pygame.init()
    pygame.display.set_caption("Tic-Tac-Toe")
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()

    FONT_LARGE = pygame.font.SysFont("consolas", 38, bold=True)
    FONT_MEDIUM = pygame.font.SysFont("consolas", 27, bold=True)
    FONT_SMALL = pygame.font.SysFont("consolas", 16, bold=True)

    audio = AudioManager()
    game = TicTacToeGame(audio)

    restart_rect = pygame.Rect(0, 0, 210, 56)
    restart_rect.center = (WINDOW_WIDTH // 2, BOARD_MARGIN_TOP + BOARD_SIZE + 46)

    ui_state = {
        "particles": [],
        "button_press_time": -9999,
        "button_scale": 1.0,
        "last_hovered": None,
    }

    running = True
    while running:
        now = pygame.time.get_ticks()
        mouse_pos = pygame.mouse.get_pos()

        running = handle_events(game, audio, restart_rect, ui_state)

        hovered_index = get_hovered_cell(mouse_pos)

        # subtle hover tick sound when moving onto a new empty cell
        if (hovered_index is not None and hovered_index != ui_state["last_hovered"]
                and not game.game_over and game.board[hovered_index] is None):
            audio.play("hover")
        ui_state["last_hovered"] = hovered_index

        # spawn confetti exactly once, right when a (non-draw) win happens
        if game.game_over and game.winner not in (None, "DRAW") and not game.confetti_spawned:
            cx, cy = WINDOW_WIDTH // 2, BOARD_MARGIN_TOP + BOARD_SIZE // 2
            ui_state["particles"].extend(spawn_confetti(cx, cy, now))
            game.confetti_spawned = True

        # update + prune particles
        ui_state["particles"] = [p for p in ui_state["particles"] if p.alive(now)]
        for p in ui_state["particles"]:
            p.update()

        # animate restart button: springy hover-grow + press-shrink
        button_hovered = restart_rect.collidepoint(mouse_pos)
        target_scale = 1.06 if button_hovered else 1.0
        press_elapsed = now - ui_state["button_press_time"]
        is_pressed = press_elapsed < 140
        if is_pressed:
            target_scale = 0.9
        ui_state["button_scale"] += (target_scale - ui_state["button_scale"]) * 0.35

        draw_all(
            screen, game, hovered_index, restart_rect, mouse_pos, now,
            ui_state["particles"], ui_state["button_scale"], is_pressed,
        )

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()