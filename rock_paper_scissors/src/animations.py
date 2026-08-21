"""
Time-based animation primitives.

Everything here is driven by delta-time (`dt`, in seconds) or by wall-clock
timestamps (`pygame.time.get_ticks()`, in milliseconds), never by raw frame
counts - so the game feels the same regardless of frame rate.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pygame

from .utils import clamp01, ease_out_cubic


@dataclass
class Tween:
    """A simple start -> end value animated over `duration` seconds."""

    start: float
    end: float
    duration: float
    easing: callable = ease_out_cubic
    delay: float = 0.0
    elapsed: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.elapsed = -self.delay
        self.duration = max(0.0001, self.duration)

    def update(self, dt: float) -> None:
        self.elapsed += dt

    @property
    def value(self) -> float:
        if self.elapsed < 0:
            return self.start
        t = clamp01(self.elapsed / self.duration)
        return self.start + (self.end - self.start) * self.easing(t)

    @property
    def done(self) -> bool:
        return self.elapsed >= self.duration


class Particle:
    """A small rotating rectangle used for confetti / sparkle effects."""

    __slots__ = ("x", "y", "vx", "vy", "color", "size", "life", "age", "gravity", "angle", "spin")

    def __init__(
        self,
        x: float,
        y: float,
        color: tuple[int, int, int],
        speed_range: tuple[float, float] = (2.0, 6.5),
        life: float = 1.0,
        gravity: float = 9.0,
        size_range: tuple[float, float] = (3.0, 7.0),
    ) -> None:
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(*speed_range)
        self.x = x
        self.y = y
        self.vx = math.cos(angle) * speed * 30
        self.vy = math.sin(angle) * speed * 30 - speed * 30 * 0.5
        self.color = color
        self.size = random.uniform(*size_range)
        self.life = life
        self.age = 0.0
        self.gravity = gravity
        self.angle = random.uniform(0, 360)
        self.spin = random.uniform(-220, 220)

    def update(self, dt: float) -> None:
        self.vy += self.gravity * 30 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt
        self.age += dt

    @property
    def alive(self) -> bool:
        return self.age < self.life

    def draw(self, surface: pygame.Surface) -> None:
        t = clamp01(self.age / self.life)
        alpha = int(255 * (1 - t))
        if alpha <= 0:
            return
        s = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, self.size, self.size * 1.5)
        rect.center = (self.size, self.size)
        pygame.draw.rect(s, (*self.color, alpha), rect, border_radius=2)
        rotated = pygame.transform.rotate(s, self.angle)
        r = rotated.get_rect(center=(self.x, self.y))
        surface.blit(rotated, r)


class ParticleSystem:
    """Owns and updates every active particle burst on screen."""

    def __init__(self) -> None:
        self.particles: list[Particle] = []

    def spawn_burst(
        self,
        x: float,
        y: float,
        colors: list[tuple[int, int, int]],
        count: int = 40,
        **particle_kwargs,
    ) -> None:
        for _ in range(count):
            color = random.choice(colors)
            self.particles.append(Particle(x, y, color, **particle_kwargs))

    def update(self, dt: float) -> None:
        for p in self.particles:
            p.update(dt)
        if self.particles:
            self.particles = [p for p in self.particles if p.alive]

    def draw(self, surface: pygame.Surface) -> None:
        for p in self.particles:
            p.draw(surface)

    def clear(self) -> None:
        self.particles.clear()
