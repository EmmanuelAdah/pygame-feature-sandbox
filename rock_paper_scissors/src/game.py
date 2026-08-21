"""
The main Game controller.

Implements a clean state machine (MENU / HOW_TO_PLAY / SETTINGS /
MODE_SELECT / PLAYING / PAUSED / MATCH_OVER) rather than one giant loop
full of unrelated conditionals. Gameplay itself is further broken into
round "phases" (CHOOSING -> COUNTDOWN -> CYCLING -> REVEAL -> RESULT),
each with time-based (not frame-based) animation.

Rendering uses a fixed 1280x720 internal surface that is scaled and
letterboxed to whatever the actual window size is, so fullscreen and
window-resizing "just work" without re-deriving every layout coordinate.
"""

from __future__ import annotations

import random
import sys

import pygame

from . import settings as cfg
from .animations import ParticleSystem
from .assets import AssetManager
from .sound import SoundManager
from .ui import Button, Slider, ToggleButton
from .utils import (
    draw_text,
    ease_out_cubic,
    radial_vignette,
    scale_image_keep_aspect,
)

Choice = cfg.Choice


def determine_winner(player: Choice, computer: Choice) -> str:
    """Return 'player', 'computer', or 'draw'."""
    if player == computer:
        return "draw"
    if cfg.BEATS[player] == computer:
        return "player"
    return "computer"


class ScoreManager:
    """Tracks a single match's score and drives the score-pop animation."""

    def __init__(self, target: int = cfg.DEFAULT_MATCH_TARGET) -> None:
        self.target = target
        self.player = 0
        self.computer = 0
        self.draws = 0
        self.round_number = 1
        self.player_pop_time = -9999
        self.computer_pop_time = -9999

    def reset(self, target: int | None = None) -> None:
        if target is not None:
            self.target = target
        self.player = 0
        self.computer = 0
        self.draws = 0
        self.round_number = 1
        self.player_pop_time = -9999
        self.computer_pop_time = -9999

    def apply_result(self, outcome: str, now_ms: int) -> None:
        if outcome == "player":
            self.player += 1
            self.player_pop_time = now_ms
        elif outcome == "computer":
            self.computer += 1
            self.computer_pop_time = now_ms
        else:
            self.draws += 1
        self.round_number += 1

    def match_over(self) -> bool:
        return self.player >= self.target or self.computer >= self.target

    def match_winner(self) -> str | None:
        if self.player >= self.target:
            return "player"
        if self.computer >= self.target:
            return "computer"
        return None


class Game:
    """Owns the window, the state machine, and every screen's widgets."""

    def __init__(self) -> None:
        pygame.init()
        flags = pygame.RESIZABLE
        self.screen = pygame.display.set_mode((cfg.SCREEN_WIDTH, cfg.SCREEN_HEIGHT), flags)
        pygame.display.set_caption(cfg.TITLE)
        self.clock = pygame.time.Clock()
        self.is_fullscreen = False
        self._windowed_size = (cfg.SCREEN_WIDTH, cfg.SCREEN_HEIGHT)

        # Fixed internal render target - scaled to the real window each frame.
        self.internal = pygame.Surface((cfg.SCREEN_WIDTH, cfg.SCREEN_HEIGHT))
        self._present_offset = (0, 0)
        self._present_scale = 1.0

        self.assets = AssetManager()
        self.sound = SoundManager()

        self._load_fonts()
        self._prep_static_surfaces()

        self.state = cfg.GameState.MENU
        self._previous_state = cfg.GameState.MENU
        self.round_phase = cfg.RoundPhase.CHOOSING
        self.running = True

        self.particles = ParticleSystem()
        self.score = ScoreManager()
        self.selected_target = cfg.DEFAULT_MATCH_TARGET

        self.player_choice: Choice | None = None
        self.computer_choice: Choice | None = None
        self.cycling_display: Choice = Choice.ROCK
        self.last_outcome: str | None = None

        # `game_time_ms` only advances while actively PLAYING (see `_update`),
        # so pausing never causes round-phase timers to "jump" once resumed -
        # unlike raw `pygame.time.get_ticks()`, which keeps ticking during a
        # pause and would otherwise let the whole round skip ahead.
        self.game_time_ms = 0.0
        self.phase_start_time = 0.0
        self.countdown_ticks_played = -1
        self.result_particles_spawned = False

        self._build_all_buttons()
        self.sound.start_music()

    # ---- setup -----------------------------------------------------------

    def _load_fonts(self) -> None:
        self.font_title = pygame.font.SysFont("georgia", 46, bold=True)
        self.font_h1 = pygame.font.SysFont("georgia", 34, bold=True)
        self.font_h2 = pygame.font.SysFont("consolas", 26, bold=True)
        self.font_body = pygame.font.SysFont("consolas", 20, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 16, bold=True)
        self.font_score = pygame.font.SysFont("consolas", 44, bold=True)
        self.font_result = pygame.font.SysFont("georgia", 40, bold=True)

    def _prep_static_surfaces(self) -> None:
        self.background_img = self.assets.get("background")
        self.vignette = radial_vignette((cfg.SCREEN_WIDTH, cfg.SCREEN_HEIGHT), strength=150)
        self.logo_img = self.assets.get("logo")

        choice_max = (190, 190)
        self.choice_images = {
            Choice.ROCK: scale_image_keep_aspect(self.assets.get("rock"), *choice_max),
            Choice.PAPER: scale_image_keep_aspect(self.assets.get("paper"), *choice_max),
            Choice.SCISSORS: scale_image_keep_aspect(self.assets.get("scissors"), *choice_max),
        }
        icon_max = (46, 46)
        self.icon_images = {
            Choice.ROCK: scale_image_keep_aspect(self.assets.get("rock"), *icon_max),
            Choice.PAPER: scale_image_keep_aspect(self.assets.get("paper"), *icon_max),
            Choice.SCISSORS: scale_image_keep_aspect(self.assets.get("scissors"), *icon_max),
        }

    # ---- button construction ------------------------------------------

    def _build_all_buttons(self) -> None:
        self._build_menu_buttons()
        self._build_mode_buttons()
        self._build_howto_buttons()
        self._build_settings_widgets()
        self._build_playing_buttons()
        self._build_pause_buttons()
        self._build_matchover_buttons()

    def _build_menu_buttons(self) -> None:
        cx = cfg.SCREEN_WIDTH // 2
        w, h, gap = 320, 62, 20
        y0 = 400
        self.menu_buttons = [
            Button((cx - w // 2, y0, w, h), "PLAY GAME", self.font_h2,
                   on_click=self._go_mode_select, sound_manager=self.sound),
            Button((cx - w // 2, y0 + (h + gap), w, h), "HOW TO PLAY", self.font_h2,
                   on_click=self._go_howto, sound_manager=self.sound),
            Button((cx - w // 2, y0 + 2 * (h + gap), w, h), "SETTINGS", self.font_h2,
                   on_click=self._go_settings, sound_manager=self.sound),
            Button((cx - w // 2, y0 + 3 * (h + gap), w, h), "EXIT", self.font_h2,
                   on_click=self._quit, sound_manager=self.sound),
        ]

    def _build_mode_buttons(self) -> None:
        cx = cfg.SCREEN_WIDTH // 2
        w, h, gap = 260, 70, 24
        total_w = len(cfg.MATCH_TARGETS) * w + (len(cfg.MATCH_TARGETS) - 1) * gap
        start_x = cx - total_w // 2
        y = 360
        self.mode_buttons = []
        for i, target in enumerate(cfg.MATCH_TARGETS):
            x = start_x + i * (w + gap)
            self.mode_buttons.append(
                Button(
                    (x, y, w, h), f"FIRST TO {target}", self.font_h2,
                    on_click=lambda t=target: self._start_match(t),
                    sound_manager=self.sound,
                )
            )
        self.mode_back_button = Button(
            (cx - 110, 520, 220, 54), "BACK", self.font_body,
            on_click=self._back_to_menu, sound_manager=self.sound,
        )

    def _build_howto_buttons(self) -> None:
        self.howto_back_button = Button(
            (cfg.SCREEN_WIDTH // 2 - 110, 650, 220, 54), "BACK", self.font_body,
            on_click=self._back_to_menu, sound_manager=self.sound,
        )

    def _build_settings_widgets(self) -> None:
        cx = cfg.SCREEN_WIDTH // 2
        w, h = 300, 56
        self.music_toggle = ToggleButton(
            (cx - w // 2, 300, w, h), "Music",
            get_state=lambda: self.sound.music_enabled,
            on_click=self._toggle_music, font=self.font_body, sound_manager=self.sound,
        )
        self.sfx_toggle = ToggleButton(
            (cx - w // 2, 372, w, h), "Sound FX",
            get_state=lambda: self.sound.sfx_enabled,
            on_click=self._toggle_sfx, font=self.font_body, sound_manager=self.sound,
        )
        self.volume_slider = Slider(
            (cx - 150, 470, 300, 12), value=cfg.SFX_VOLUME, on_change=self._set_volume,
        )
        self.settings_back_button = Button(
            (cx - 110, 560, 220, 54), "BACK", self.font_body,
            on_click=self._back_to_menu, sound_manager=self.sound,
        )

    def _build_playing_buttons(self) -> None:
        w, h, gap = 190, 140, 36
        total_w = 3 * w + 2 * gap
        start_x = cfg.SCREEN_WIDTH // 2 - total_w // 2
        y = 410
        self.choice_buttons: dict[Choice, Button] = {}
        for i, choice in enumerate(cfg.CHOICES):
            x = start_x + i * (w + gap)
            self.choice_buttons[choice] = Button(
                (x, y, w, h), choice.label, self.font_body,
                on_click=lambda c=choice: self._player_choose(c),
                icon=self.icon_images[choice],
                sound_manager=self.sound,
                base_color=(34, 38, 54), hover_color=(50, 56, 78),
            )

    def _build_pause_buttons(self) -> None:
        cx = cfg.SCREEN_WIDTH // 2
        w, h, gap = 280, 60, 18
        y0 = 365
        self.pause_buttons = [
            Button((cx - w // 2, y0, w, h), "RESUME", self.font_h2,
                   on_click=self._resume_game, sound_manager=self.sound),
            Button((cx - w // 2, y0 + (h + gap), w, h), "RESTART MATCH", self.font_body,
                   on_click=self._restart_match, sound_manager=self.sound),
            Button((cx - w // 2, y0 + 2 * (h + gap), w, h), "MAIN MENU", self.font_body,
                   on_click=self._back_to_menu, sound_manager=self.sound),
        ]

    def _build_matchover_buttons(self) -> None:
        cx = cfg.SCREEN_WIDTH // 2
        w, h, gap = 280, 60, 20
        y0 = 470
        self.matchover_buttons = [
            Button((cx - w // 2, y0, w, h), "PLAY AGAIN", self.font_h2,
                   on_click=self._replay_match, sound_manager=self.sound),
            Button((cx - w // 2, y0 + (h + gap), w, h), "MAIN MENU", self.font_body,
                   on_click=self._back_to_menu, sound_manager=self.sound),
        ]

    # ---- navigation callbacks ------------------------------------------

    def _go_mode_select(self) -> None:
        self.state = cfg.GameState.MODE_SELECT

    def _go_howto(self) -> None:
        self._previous_state = self.state
        self.state = cfg.GameState.HOW_TO_PLAY

    def _go_settings(self) -> None:
        self._previous_state = self.state
        self.state = cfg.GameState.SETTINGS

    def _back_to_menu(self) -> None:
        self.state = cfg.GameState.MENU

    def _quit(self) -> None:
        self.running = False

    def _toggle_music(self) -> None:
        self.sound.toggle_music()

    def _toggle_sfx(self) -> None:
        self.sound.toggle_sfx()

    def _set_volume(self, value: float) -> None:
        self.sound.set_sfx_volume(value)
        self.sound.set_music_volume(value * 0.55)  # keep music under SFX by default

    def _start_match(self, target: int) -> None:
        self.selected_target = target
        self.score.reset(target)
        self.state = cfg.GameState.PLAYING
        self._start_round()

    def _replay_match(self) -> None:
        self._start_match(self.selected_target)

    def _restart_match(self) -> None:
        self._start_match(self.selected_target)

    def _resume_game(self) -> None:
        self.state = cfg.GameState.PLAYING

    def _pause_game(self) -> None:
        self._previous_state = self.state
        self.state = cfg.GameState.PAUSED

    # ---- round flow -----------------------------------------------------

    def _start_round(self) -> None:
        self.round_phase = cfg.RoundPhase.CHOOSING
        self.player_choice = None
        self.computer_choice = random.choice(cfg.CHOICES)  # predetermined, revealed later
        self.cycling_display = random.choice(cfg.CHOICES)
        self.last_outcome = None
        self.result_particles_spawned = False
        self.phase_start_time = self.game_time_ms
        self.countdown_ticks_played = -1
        self.sound.play_round_start()

    def _player_choose(self, choice: Choice) -> None:
        if self.round_phase != cfg.RoundPhase.CHOOSING:
            return
        self.player_choice = choice
        self.round_phase = cfg.RoundPhase.COUNTDOWN
        self.phase_start_time = self.game_time_ms
        self.countdown_ticks_played = -1

    def _update_round_phase(self, now_ms: float) -> None:
        elapsed = now_ms - self.phase_start_time

        if self.round_phase == cfg.RoundPhase.COUNTDOWN:
            tick_index = int(elapsed // cfg.COUNTDOWN_STEP_MS)
            if tick_index > self.countdown_ticks_played and tick_index <= 2:
                self.countdown_ticks_played = tick_index
                self.sound.play_countdown()
            if elapsed >= cfg.COUNTDOWN_STEP_MS * 3:
                self.round_phase = cfg.RoundPhase.CYCLING
                self.phase_start_time = now_ms

        elif self.round_phase == cfg.RoundPhase.CYCLING:
            step = elapsed // cfg.CYCLING_STEP_MS
            idx = int(step) % len(cfg.CHOICES)
            self.cycling_display = cfg.CHOICES[idx]
            if elapsed >= cfg.CYCLING_DURATION_MS:
                self.round_phase = cfg.RoundPhase.REVEAL
                self.phase_start_time = now_ms
                self.sound.play_reveal()

        elif self.round_phase == cfg.RoundPhase.REVEAL:
            if elapsed >= cfg.REVEAL_DURATION_MS:
                self.round_phase = cfg.RoundPhase.RESULT
                self.phase_start_time = now_ms
                self.last_outcome = determine_winner(self.player_choice, self.computer_choice)
                self._apply_round_result(now_ms)

        elif self.round_phase == cfg.RoundPhase.RESULT:
            if elapsed >= cfg.RESULT_HOLD_MS:
                if self.score.match_over():
                    self._enter_match_over()
                else:
                    self._start_round()

    def _apply_round_result(self, now_ms: float) -> None:
        self.score.apply_result(self.last_outcome, now_ms)

        player_rect = self._player_image_rect()
        computer_rect = self._computer_image_rect()

        if self.last_outcome == "player":
            self.sound.play_win()
            cx, cy = player_rect.center
            self.particles.spawn_burst(cx, cy, [cfg.COLOR_WIN, cfg.COLOR_GOLD, (255, 255, 255)], count=55)
        elif self.last_outcome == "computer":
            self.sound.play_loss()
            cx, cy = computer_rect.center
            self.particles.spawn_burst(cx, cy, [cfg.COLOR_LOSS, (120, 60, 60), (200, 200, 200)], count=45)
        else:
            self.sound.play_draw()
            cx = cfg.SCREEN_WIDTH // 2
            cy = (player_rect.centery + computer_rect.centery) // 2
            self.particles.spawn_burst(cx, cy, [cfg.COLOR_DRAW, (255, 255, 255)], count=28, speed_range=(1.5, 4.0))

    def _enter_match_over(self) -> None:
        self.state = cfg.GameState.MATCH_OVER
        if self.score.match_winner() == "player":
            self.sound.play_match_win()
        else:
            self.sound.play_match_loss()

    # ---- layout helpers ---------------------------------------------------

    def _player_image_rect(self) -> pygame.Rect:
        size = 210
        return pygame.Rect(0, 0, size, size).move(
            cfg.SCREEN_WIDTH // 2 - 300 - size // 2, 82
        )

    def _computer_image_rect(self) -> pygame.Rect:
        size = 210
        return pygame.Rect(0, 0, size, size).move(
            cfg.SCREEN_WIDTH // 2 + 300 - size // 2, 82
        )

    # ---- main loop --------------------------------------------------------

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(cfg.FPS) / 1000.0
            self._handle_events()
            self._update(dt)
            self._draw()
            self._present()
        pygame.quit()
        sys.exit()

    # ---- event handling -----------------------------------------------

    def _get_internal_mouse_pos(self) -> tuple[float, float]:
        mx, my = pygame.mouse.get_pos()
        off_x, off_y = self._present_offset
        scale = self._present_scale or 1.0
        return ((mx - off_x) / scale, (my - off_y) / scale)

    def _handle_events(self) -> None:
        mouse_pos = self._get_internal_mouse_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.VIDEORESIZE:
                if not self.is_fullscreen:
                    self._windowed_size = (event.w, event.h)
                self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)

            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event.key)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(mouse_pos)

            if self.state == cfg.GameState.SETTINGS:
                self.volume_slider.handle_event(event, mouse_pos_override=mouse_pos)

    def _handle_keydown(self, key: int) -> None:
        if key == pygame.K_F11:
            self._toggle_fullscreen()
            return

        if key == pygame.K_m:
            self.sound.toggle_music()
            return

        if key == pygame.K_ESCAPE:
            if self.state == cfg.GameState.PLAYING:
                self._pause_game()
            elif self.state == cfg.GameState.PAUSED:
                self._resume_game()
            elif self.state in (cfg.GameState.HOW_TO_PLAY, cfg.GameState.SETTINGS):
                self._back_to_menu()
            return

        if self.state == cfg.GameState.PLAYING and self.round_phase == cfg.RoundPhase.CHOOSING:
            key_map = {
                pygame.K_r: Choice.ROCK,
                pygame.K_p: Choice.PAPER,
                pygame.K_s: Choice.SCISSORS,
            }
            if key in key_map:
                self._player_choose(key_map[key])

    def _toggle_fullscreen(self) -> None:
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode(self._windowed_size, pygame.RESIZABLE)

    def _handle_click(self, mouse_pos: tuple[float, float]) -> None:
        state = self.state
        if state == cfg.GameState.MENU:
            for b in self.menu_buttons:
                if b.handle_click(mouse_pos):
                    return
        elif state == cfg.GameState.MODE_SELECT:
            for b in self.mode_buttons:
                if b.handle_click(mouse_pos):
                    return
            self.mode_back_button.handle_click(mouse_pos)
        elif state == cfg.GameState.HOW_TO_PLAY:
            self.howto_back_button.handle_click(mouse_pos)
        elif state == cfg.GameState.SETTINGS:
            self.music_toggle.handle_click(mouse_pos)
            self.sfx_toggle.handle_click(mouse_pos)
            self.settings_back_button.handle_click(mouse_pos)
        elif state == cfg.GameState.PLAYING:
            if self.round_phase == cfg.RoundPhase.CHOOSING:
                for b in self.choice_buttons.values():
                    if b.handle_click(mouse_pos):
                        return
        elif state == cfg.GameState.PAUSED:
            for b in self.pause_buttons:
                if b.handle_click(mouse_pos):
                    return
        elif state == cfg.GameState.MATCH_OVER:
            for b in self.matchover_buttons:
                if b.handle_click(mouse_pos):
                    return

    # ---- update ------------------------------------------------------

    def _update(self, dt: float) -> None:
        mouse_pos = self._get_internal_mouse_pos()

        # Only the PLAYING state advances the pause-safe game clock, so a
        # paused round resumes exactly where it left off instead of skipping
        # ahead by however long the pause menu was open.
        if self.state == cfg.GameState.PLAYING:
            self.game_time_ms += dt * 1000.0

        if self.state != cfg.GameState.PAUSED:
            self.particles.update(dt)

        buttons_by_state = {
            cfg.GameState.MENU: self.menu_buttons,
            cfg.GameState.MODE_SELECT: self.mode_buttons + [self.mode_back_button],
            cfg.GameState.HOW_TO_PLAY: [self.howto_back_button],
            cfg.GameState.SETTINGS: [self.music_toggle, self.sfx_toggle, self.settings_back_button],
            cfg.GameState.PAUSED: self.pause_buttons,
            cfg.GameState.MATCH_OVER: self.matchover_buttons,
        }
        active = buttons_by_state.get(self.state)
        if active:
            for b in active:
                b.update(dt, mouse_pos)

        if self.state == cfg.GameState.PLAYING:
            if self.round_phase == cfg.RoundPhase.CHOOSING:
                for b in self.choice_buttons.values():
                    b.update(dt, mouse_pos)
            self._update_round_phase(self.game_time_ms)

    # ---- drawing --------------------------------------------------------

    def _draw_background(self) -> None:
        self.internal.blit(self.background_img, (0, 0))
        self.internal.blit(self.vignette, (0, 0))

    def _draw(self) -> None:
        self._draw_background()

        if self.state == cfg.GameState.MENU:
            self._draw_menu()
        elif self.state == cfg.GameState.MODE_SELECT:
            self._draw_mode_select()
        elif self.state == cfg.GameState.HOW_TO_PLAY:
            self._draw_howto()
        elif self.state == cfg.GameState.SETTINGS:
            self._draw_settings()
        elif self.state == cfg.GameState.PLAYING:
            self._draw_playing()
        elif self.state == cfg.GameState.PAUSED:
            self._draw_playing(dim=True)
            self._draw_pause_overlay()
        elif self.state == cfg.GameState.MATCH_OVER:
            self._draw_playing(dim=True)
            self._draw_matchover_overlay()

    # -- Menu --

    def _draw_menu(self) -> None:
        now_ms = pygame.time.get_ticks()
        bob = int(4 * __import__("math").sin(now_ms / 500.0))
        logo_rect = self.logo_img.get_rect(center=(cfg.SCREEN_WIDTH // 2, 190 + bob))
        self.internal.blit(self.logo_img, logo_rect)

        draw_text(
            self.internal, "Choose your move. Challenge the computer.",
            self.font_body, cfg.COLOR_SUBTEXT, (cfg.SCREEN_WIDTH // 2, 270),
        )

        for b in self.menu_buttons:
            b.draw(self.internal)

    # -- Mode select --

    def _draw_mode_select(self) -> None:
        draw_text(self.internal, "CHOOSE MATCH LENGTH", self.font_h1, cfg.COLOR_TEXT,
                  (cfg.SCREEN_WIDTH // 2, 220))
        draw_text(self.internal, "First to win the target number of rounds takes the match.",
                  self.font_body, cfg.COLOR_SUBTEXT, (cfg.SCREEN_WIDTH // 2, 270))
        for b in self.mode_buttons:
            b.draw(self.internal)
        self.mode_back_button.draw(self.internal)

    # -- How to play --

    def _draw_howto(self) -> None:
        draw_text(self.internal, "HOW TO PLAY", self.font_h1, cfg.COLOR_TEXT,
                  (cfg.SCREEN_WIDTH // 2, 90))

        rules = [
            (Choice.ROCK, Choice.SCISSORS, "Rock beats Scissors"),
            (Choice.SCISSORS, Choice.PAPER, "Scissors beat Paper"),
            (Choice.PAPER, Choice.ROCK, "Paper beats Rock"),
        ]
        row_y = 190
        row_spacing = 128
        icon_size = (76, 76)
        for winner, loser, label in rules:
            row_center_x = cfg.SCREEN_WIDTH // 2
            win_img = scale_image_keep_aspect(self.assets.get(winner.value), *icon_size)
            lose_img = scale_image_keep_aspect(self.assets.get(loser.value), *icon_size)

            win_rect = win_img.get_rect(center=(row_center_x - 160, row_y))
            lose_rect = lose_img.get_rect(center=(row_center_x + 160, row_y))
            self.internal.blit(win_img, win_rect)
            self.internal.blit(lose_img, lose_rect)

            draw_text(self.internal, ">", self.font_h1, cfg.COLOR_GOLD, (row_center_x, row_y))
            draw_text(self.internal, label, self.font_body, cfg.COLOR_TEXT, (row_center_x, row_y + 58))
            row_y += row_spacing

        controls = [
            "R = Rock     P = Paper     S = Scissors",
            "ESC = Pause     M = Toggle Music     F11 = Fullscreen",
        ]
        y = 570
        for line in controls:
            draw_text(self.internal, line, self.font_small, cfg.COLOR_SUBTEXT, (cfg.SCREEN_WIDTH // 2, y))
            y += 24

        self.howto_back_button.draw(self.internal)

    # -- Settings --

    def _draw_settings(self) -> None:
        draw_text(self.internal, "SETTINGS", self.font_h1, cfg.COLOR_TEXT, (cfg.SCREEN_WIDTH // 2, 220))
        self.music_toggle.draw(self.internal)
        self.sfx_toggle.draw(self.internal)

        draw_text(self.internal, "VOLUME", self.font_small, cfg.COLOR_SUBTEXT,
                  (cfg.SCREEN_WIDTH // 2, 448))
        self.volume_slider.draw(self.internal)

        self.settings_back_button.draw(self.internal)

    # -- Playing (gameplay screen) --

    def _draw_playing(self, dim: bool = False) -> None:
        now_ms = self.game_time_ms

        draw_text(self.internal, "ROCK  •  PAPER  •  SCISSORS", self.font_h2, cfg.COLOR_TEXT,
                  (cfg.SCREEN_WIDTH // 2, 26))
        draw_text(self.internal, f"ROUND {self.score.round_number}", self.font_small,
                  cfg.COLOR_SUBTEXT, (cfg.SCREEN_WIDTH // 2, 52))

        player_rect = self._player_image_rect()
        computer_rect = self._computer_image_rect()

        draw_text(self.internal, "PLAYER", self.font_body, cfg.COLOR_ACCENT,
                  (player_rect.centerx, player_rect.top - 20))
        draw_text(self.internal, "COMPUTER", self.font_body, cfg.COLOR_LOSS,
                  (computer_rect.centerx, computer_rect.top - 20))
        draw_text(self.internal, "VS", self.font_h1, cfg.COLOR_GOLD,
                  (cfg.SCREEN_WIDTH // 2, player_rect.centery))

        self._draw_choice_slot(player_rect, self._current_player_display(), is_player=True, now_ms=now_ms)
        self._draw_choice_slot(computer_rect, self._current_computer_display(), is_player=False, now_ms=now_ms)

        if not dim:
            self._draw_round_status(now_ms)
        self._draw_scoreboard(now_ms)

        if self.round_phase == cfg.RoundPhase.CHOOSING and not dim:
            for b in self.choice_buttons.values():
                b.draw(self.internal)
        elif not dim:
            draw_text(
                self.internal, "Choose your weapon",
                self.font_small, (70, 74, 90), (cfg.SCREEN_WIDTH // 2, 480),
            )

        self.particles.draw(self.internal)

        if dim:
            overlay = pygame.Surface((cfg.SCREEN_WIDTH, cfg.SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 195))
            self.internal.blit(overlay, (0, 0))

    def _current_player_display(self) -> Choice | None:
        return self.player_choice

    def _current_computer_display(self) -> Choice | None:
        if self.round_phase in (cfg.RoundPhase.CHOOSING, cfg.RoundPhase.COUNTDOWN):
            return None
        if self.round_phase == cfg.RoundPhase.CYCLING:
            return self.cycling_display
        return self.computer_choice

    def _draw_choice_slot(self, rect: pygame.Rect, choice: Choice | None, is_player: bool, now_ms: float) -> None:
        panel = pygame.Rect(0, 0, 210, 210)
        panel.center = rect.center
        pygame.draw.rect(self.internal, cfg.COLOR_PANEL, panel, border_radius=20)
        pygame.draw.rect(self.internal, (60, 66, 90), panel, width=2, border_radius=20)

        if choice is None:
            draw_text(self.internal, "?", self.font_title, (70, 76, 96), panel.center)
            return

        img = self.choice_images[choice]

        scale = 1.0
        elapsed = now_ms - self.phase_start_time

        if self.round_phase == cfg.RoundPhase.REVEAL:
            t = ease_out_cubic(min(1.0, elapsed / cfg.REVEAL_DURATION_MS))
            scale = 0.3 + 0.7 * t
            # Slide slightly toward center as they "approach" each other.
            approach = (1 - t) * 26
            offset = -approach if is_player else approach
            panel = panel.move(offset, 0)
        elif self.round_phase == cfg.RoundPhase.RESULT:
            is_winner = (
                (is_player and self.last_outcome == "player")
                or (not is_player and self.last_outcome == "computer")
            )
            is_loser = (
                (is_player and self.last_outcome == "computer")
                or (not is_player and self.last_outcome == "player")
            )
            if is_winner:
                pulse = 0.5 + 0.5 * __import__("math").sin(now_ms / 130.0)
                scale = 1.08 + 0.06 * pulse
                glow = pygame.Surface(panel.size, pygame.SRCALPHA)
                pygame.draw.rect(glow, (*cfg.COLOR_GOLD, 70), glow.get_rect(), border_radius=20)
                self.internal.blit(glow, panel.topleft)
            elif is_loser:
                scale = 0.88

        w, h = int(img.get_width() * scale), int(img.get_height() * scale)
        if w > 0 and h > 0:
            scaled_img = pygame.transform.smoothscale(img, (w, h))
            img_rect = scaled_img.get_rect(center=panel.center)
            self.internal.blit(scaled_img, img_rect)

    def _draw_round_status(self, now_ms: float) -> None:
        cy = 350
        if self.round_phase == cfg.RoundPhase.COUNTDOWN:
            elapsed = now_ms - self.phase_start_time
            number = 3 - min(2, elapsed // cfg.COUNTDOWN_STEP_MS)
            step_progress = (elapsed % cfg.COUNTDOWN_STEP_MS) / cfg.COUNTDOWN_STEP_MS
            scale = 1.0 + 0.5 * (1 - ease_out_cubic(step_progress))
            text = str(int(max(1, number)))
            font = self.font_title
            surf = font.render(text, True, cfg.COLOR_GOLD)
            if scale != 1.0:
                w, h = surf.get_size()
                surf = pygame.transform.smoothscale(surf, (max(1, int(w * scale)), max(1, int(h * scale))))
            rect = surf.get_rect(center=(cfg.SCREEN_WIDTH // 2, cy))
            self.internal.blit(surf, rect)

        elif self.round_phase == cfg.RoundPhase.RESULT:
            elapsed = now_ms - self.phase_start_time
            pop_t = min(1.0, elapsed / cfg.SCORE_POP_MS)
            scale = 1.0 + 0.3 * (1 - ease_out_cubic(pop_t))
            label, color = {
                "player": ("YOU WIN!", cfg.COLOR_WIN),
                "computer": ("COMPUTER WINS!", cfg.COLOR_LOSS),
                "draw": ("DRAW!", cfg.COLOR_DRAW),
            }[self.last_outcome]
            surf = self.font_result.render(label, True, color)
            if scale != 1.0:
                w, h = surf.get_size()
                surf = pygame.transform.smoothscale(surf, (max(1, int(w * scale)), max(1, int(h * scale))))
            rect = surf.get_rect(center=(cfg.SCREEN_WIDTH // 2, cy))
            self.internal.blit(surf, rect)

    def _draw_scoreboard(self, now_ms: float) -> None:
        y = 630
        cx = cfg.SCREEN_WIDTH // 2

        def pop_scale(pop_time: int) -> float:
            elapsed = now_ms - pop_time
            if elapsed < 0 or elapsed > cfg.SCORE_POP_MS:
                return 1.0
            return 1.0 + 0.45 * (1 - ease_out_cubic(elapsed / cfg.SCORE_POP_MS))

        self._draw_pop_number(str(self.score.player), cx - 220, y, cfg.COLOR_ACCENT,
                              pop_scale(self.score.player_pop_time))
        draw_text(self.internal, "PLAYER", self.font_small, cfg.COLOR_SUBTEXT, (cx - 220, y + 34))

        draw_text(self.internal, "-", self.font_score, cfg.COLOR_SUBTEXT, (cx, y))

        self._draw_pop_number(str(self.score.computer), cx + 220, y, cfg.COLOR_LOSS,
                              pop_scale(self.score.computer_pop_time))
        draw_text(self.internal, "COMPUTER", self.font_small, cfg.COLOR_SUBTEXT, (cx + 220, y + 34))

        draw_text(self.internal, f"Draws: {self.score.draws}   |   First to {self.score.target}",
                  self.font_small, (110, 114, 130), (cx, y + 58))

    def _draw_pop_number(self, text: str, x: int, y: int, color, scale: float) -> None:
        surf = self.font_score.render(text, True, color)
        if scale != 1.0:
            w, h = surf.get_size()
            surf = pygame.transform.smoothscale(surf, (max(1, int(w * scale)), max(1, int(h * scale))))
        rect = surf.get_rect(center=(x, y))
        self.internal.blit(surf, rect)

    # -- Pause overlay --

    def _draw_pause_overlay(self) -> None:
        draw_text(self.internal, "GAME PAUSED", self.font_title, cfg.COLOR_TEXT,
                  (cfg.SCREEN_WIDTH // 2, 320))
        for b in self.pause_buttons:
            b.draw(self.internal)

    # -- Match over overlay --

    def _draw_matchover_overlay(self) -> None:
        winner = self.score.match_winner()
        if winner == "player":
            title, color = "YOU WIN THE MATCH!", cfg.COLOR_WIN
        else:
            title, color = "COMPUTER WINS THE MATCH!", cfg.COLOR_LOSS

        draw_text(self.internal, title, self.font_title, color, (cfg.SCREEN_WIDTH // 2, 300))
        draw_text(
            self.internal, f"Final Score  —  Player {self.score.player} : {self.score.computer} Computer",
            self.font_body, cfg.COLOR_SUBTEXT, (cfg.SCREEN_WIDTH // 2, 360),
        )
        for b in self.matchover_buttons:
            b.draw(self.internal)

    # ---- presentation (scale internal surface to real window) ---------

    def _present(self) -> None:
        window_w, window_h = self.screen.get_size()
        scale = min(window_w / cfg.SCREEN_WIDTH, window_h / cfg.SCREEN_HEIGHT)
        scale = max(0.01, scale)
        scaled_w, scaled_h = int(cfg.SCREEN_WIDTH * scale), int(cfg.SCREEN_HEIGHT * scale)
        scaled_surf = pygame.transform.smoothscale(self.internal, (scaled_w, scaled_h))

        self.screen.fill((0, 0, 0))
        off_x = (window_w - scaled_w) // 2
        off_y = (window_h - scaled_h) // 2
        self.screen.blit(scaled_surf, (off_x, off_y))

        self._present_offset = (off_x, off_y)
        self._present_scale = scale

        pygame.display.flip()
