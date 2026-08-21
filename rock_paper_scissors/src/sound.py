"""
Centralized audio: sound-effect + music loading, caching, and playback.

Like :mod:`assets`, every sound prefers a real file on disk (drop a
``button_click.wav`` into ``assets/sounds`` and it will be used automatically)
and only falls back to procedural waveform synthesis when no file is present.
All sounds are generated once at startup and cached - never re-loaded or
re-synthesized during gameplay.
"""

from __future__ import annotations

import math

import numpy as np
import pygame

from . import settings as cfg
from .utils import clamp01


class SoundManager:
    SAMPLE_RATE = 44100

    def __init__(self) -> None:
        self.mixer_available = True
        self.sfx_enabled = True
        self.music_enabled = True
        self.sfx_volume = cfg.SFX_VOLUME
        self.music_volume = cfg.MUSIC_VOLUME

        self.sounds: dict[str, pygame.mixer.Sound | None] = {}
        self._music_channel: pygame.mixer.Channel | None = None

        try:
            pygame.mixer.init(frequency=self.SAMPLE_RATE, size=-16, channels=2)
            pygame.mixer.set_num_channels(24)
            self._load_all()
        except pygame.error as exc:
            print(f"Warning: audio device unavailable ({exc}). The game will run without sound.")
            self.mixer_available = False

    # ---- loading -----------------------------------------------------

    def _load_all(self) -> None:
        generators = {
            "button_hover": lambda: self._tone(1500, 0.035, 0.16, "sine"),
            "button_click": lambda: self._click(),
            "countdown": lambda: self._tone(720, 0.12, 0.4, "square", release=0.7),
            "reveal": lambda: self._sweep(320, 950, 0.25, 0.32),
            "player_win": lambda: self._fanfare([523.25, 659.25, 783.99, 1046.50], 0.13, 0.42),
            "computer_win": lambda: self._descend([392.0, 329.6, 261.6], 0.16, 0.35),
            "draw": lambda: self._tone(440, 0.3, 0.28, "triangle"),
            "round_start": lambda: self._sweep(500, 1000, 0.15, 0.22),
            "match_win": lambda: self._fanfare(
                [523.25, 659.25, 783.99, 1046.50, 1318.51], 0.15, 0.46
            ),
            "match_loss": lambda: self._descend([392.0, 311.1, 233.1, 196.0], 0.2, 0.42),
        }
        for name, generator in generators.items():
            self.sounds[name] = self._load_or_generate(f"{name}.wav", generator)
        self.sounds["music"] = self._load_or_generate_music()

    def _load_or_generate(self, filename: str, generator) -> pygame.mixer.Sound | None:
        path = cfg.SOUNDS_DIR / filename
        if path.exists():
            try:
                return pygame.mixer.Sound(str(path))
            except pygame.error as exc:
                print(f"Warning: could not load sound '{path}' ({exc}); synthesizing instead.")
        try:
            return self._to_sound(generator())
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: failed to synthesize sound '{filename}' ({exc}); it will be silent.")
            return None

    def _load_or_generate_music(self) -> pygame.mixer.Sound | None:
        for ext in ("ogg", "mp3", "wav"):
            path = cfg.MUSIC_DIR / f"background.{ext}"
            if path.exists():
                try:
                    return pygame.mixer.Sound(str(path))
                except pygame.error as exc:
                    print(f"Warning: could not load music '{path}' ({exc}); synthesizing instead.")
        try:
            return self._to_sound(self._ambient_loop())
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: failed to synthesize background music ({exc}); music disabled.")
            return None

    # ---- low-level waveform synthesis --------------------------------

    def _envelope(self, n_samples: int, attack: float = 0.02, release: float = 0.4) -> np.ndarray:
        env = np.ones(n_samples)
        attack_n = max(1, int(n_samples * attack))
        release_n = max(1, int(n_samples * release))
        env[:attack_n] = np.linspace(0, 1, attack_n)
        env[-release_n:] *= np.linspace(1, 0, release_n)
        return env

    def _tone(
        self, freq: float, duration: float, volume: float = 0.5,
        waveform: str = "sine", attack: float = 0.02, release: float = 0.5,
    ) -> np.ndarray:
        n_samples = int(self.SAMPLE_RATE * duration)
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

    def _sweep(self, start_freq: float, end_freq: float, duration: float, volume: float) -> np.ndarray:
        n_samples = int(self.SAMPLE_RATE * duration)
        t = np.linspace(0, duration, n_samples, endpoint=False)
        freq_sweep = np.linspace(start_freq, end_freq, n_samples)
        phase = np.cumsum(2 * np.pi * freq_sweep / self.SAMPLE_RATE)
        wave = np.sin(phase) * self._envelope(n_samples, attack=0.05, release=0.6)
        return wave * volume

    def _fanfare(self, notes: list[float], note_duration: float, volume: float) -> np.ndarray:
        parts = [
            self._tone(f, note_duration, volume=volume, waveform="triangle", attack=0.01, release=0.5)
            for f in notes
        ]
        return np.concatenate(parts)

    def _descend(self, notes: list[float], note_duration: float, volume: float) -> np.ndarray:
        parts = [
            self._tone(f, note_duration, volume=volume, waveform="sine", attack=0.02, release=0.6)
            for f in notes
        ]
        return np.concatenate(parts)

    def _click(self) -> np.ndarray:
        n_samples = int(self.SAMPLE_RATE * 0.05)
        noise = np.random.uniform(-1, 1, n_samples) * 0.15
        tone = self._tone(1000, 0.05, volume=0.35, waveform="square", attack=0.005, release=0.7)
        return noise + tone

    def _ambient_loop(self) -> np.ndarray:
        """A soft, seamless-looping ambient pad - low volume background music."""
        duration = 8.0
        n_samples = int(self.SAMPLE_RATE * duration)
        t = np.linspace(0, duration, n_samples, endpoint=False)

        # Use frequencies that complete a whole number of cycles in `duration`
        # seconds so the waveform loops without a click.
        chord_freqs = [110.0, 138.6, 164.8, 220.0]  # A2, C#3, E3, A3 (A major-ish pad)
        wave = np.zeros(n_samples)
        for freq in chord_freqs:
            cycles = round(freq * duration)
            adjusted_freq = cycles / duration
            wave += np.sin(2 * np.pi * adjusted_freq * t) * 0.18

        # Slow amplitude LFO so the pad gently breathes, also loop-safe.
        lfo_cycles = round(0.25 * duration)
        lfo_freq = lfo_cycles / duration
        lfo = 0.75 + 0.25 * np.sin(2 * np.pi * lfo_freq * t)
        wave *= lfo

        # Gentle overall fade at the very start/end to avoid a seam click,
        # using a tiny crossfade window rather than a hard envelope.
        fade_n = int(self.SAMPLE_RATE * 0.05)
        fade = np.linspace(0, 1, fade_n)
        wave[:fade_n] *= fade
        wave[-fade_n:] *= fade[::-1]

        return wave * 0.5

    def _to_sound(self, wave: np.ndarray) -> pygame.mixer.Sound:
        wave = np.clip(wave, -1, 1)
        mono = (wave * 32767).astype(np.int16)
        stereo = np.column_stack((mono, mono))
        return pygame.mixer.Sound(np.ascontiguousarray(stereo))

    # ---- public playback API -----------------------------------------

    def _play(self, name: str) -> None:
        if not self.mixer_available or not self.sfx_enabled:
            return
        sound = self.sounds.get(name)
        if sound is not None:
            sound.set_volume(self.sfx_volume)
            sound.play()

    def play_hover(self) -> None:
        self._play("button_hover")

    def play_click(self) -> None:
        self._play("button_click")

    def play_countdown(self) -> None:
        self._play("countdown")

    def play_reveal(self) -> None:
        self._play("reveal")

    def play_win(self) -> None:
        self._play("player_win")

    def play_loss(self) -> None:
        self._play("computer_win")

    def play_draw(self) -> None:
        self._play("draw")

    def play_round_start(self) -> None:
        self._play("round_start")

    def play_match_win(self) -> None:
        self._play("match_win")

    def play_match_loss(self) -> None:
        self._play("match_loss")

    # ---- music ---------------------------------------------------------

    def start_music(self) -> None:
        if not self.mixer_available or not self.music_enabled:
            return
        music = self.sounds.get("music")
        if music is None:
            return
        if self._music_channel is not None and self._music_channel.get_busy():
            return  # already playing
        music.set_volume(self.music_volume)
        self._music_channel = music.play(loops=-1)

    def stop_music(self) -> None:
        if self._music_channel is not None:
            self._music_channel.stop()

    def toggle_music(self) -> bool:
        self.music_enabled = not self.music_enabled
        if self.music_enabled:
            self.start_music()
        else:
            self.stop_music()
        return self.music_enabled

    def toggle_sfx(self) -> bool:
        self.sfx_enabled = not self.sfx_enabled
        return self.sfx_enabled

    def set_sfx_volume(self, value: float) -> None:
        self.sfx_volume = clamp01(value)

    def set_music_volume(self, value: float) -> None:
        self.music_volume = clamp01(value)
        if self._music_channel is not None:
            self._music_channel.set_volume(self.music_volume)
