"""Reusable, self-contained UI widgets (buttons, sliders) used across every
screen. Widgets know how to animate and draw themselves, but never own game
state - the owning screen decides what a click *means*.
"""

from __future__ import annotations

from typing import Callable, Optional

import pygame

from . import settings as cfg
from .utils import clamp01, draw_text


class Button:
    """A clickable, hover-animated button with an optional icon image."""

    def __init__(
        self,
        rect: tuple[int, int, int, int],
        text: str,
        font: pygame.font.Font,
        on_click: Optional[Callable[[], None]] = None,
        icon: Optional[pygame.Surface] = None,
        sound_manager=None,
        base_color=cfg.COLOR_BUTTON,
        hover_color=cfg.COLOR_BUTTON_HOVER,
        text_color=cfg.COLOR_TEXT,
        accent=cfg.COLOR_ACCENT,
    ) -> None:
        self.base_rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.on_click = on_click
        self.icon = icon
        self.sound_manager = sound_manager
        self.base_color = base_color
        self.hover_color = hover_color
        self.text_color = text_color
        self.accent = accent

        self.scale = 1.0
        self.hovered = False
        self._was_hovered = False
        self.enabled = True
        self.visible = True

    def set_text(self, text: str) -> None:
        self.text = text

    def update(self, dt: float, mouse_pos: tuple[float, float]) -> bool:
        if not self.visible:
            self.hovered = False
            return False
        self.hovered = self.enabled and self.base_rect.collidepoint(mouse_pos)
        target = 1.06 if self.hovered else 1.0
        self.scale += (target - self.scale) * min(1.0, dt * cfg.BUTTON_HOVER_LERP)
        if self.hovered and not self._was_hovered and self.sound_manager:
            self.sound_manager.play_hover()
        self._was_hovered = self.hovered
        return self.hovered

    def handle_click(self, mouse_pos: tuple[float, float]) -> bool:
        if not self.visible or not self.enabled:
            return False
        if self.base_rect.collidepoint(mouse_pos):
            if self.sound_manager:
                self.sound_manager.play_click()
            if self.on_click:
                self.on_click()
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return

        w = max(1, int(self.base_rect.width * self.scale))
        h = max(1, int(self.base_rect.height * self.scale))
        rect = pygame.Rect(0, 0, w, h)
        rect.center = self.base_rect.center

        shadow_rect = rect.move(0, 4)
        pygame.draw.rect(surface, (6, 7, 12), shadow_rect, border_radius=14)

        color = self.hover_color if self.hovered else self.base_color
        pygame.draw.rect(surface, color, rect, border_radius=14)

        border_color = self.accent if self.hovered else (86, 92, 116)
        pygame.draw.rect(surface, border_color, rect, width=2, border_radius=14)

        text_color = self.text_color if self.enabled else cfg.COLOR_SUBTEXT

        if self.icon:
            icon_rect = self.icon.get_rect()
            label_surf = self.font.render(self.text, True, text_color)
            total_w = icon_rect.width + 12 + label_surf.get_width()
            start_x = rect.centerx - total_w // 2
            icon_rect.midleft = (start_x, rect.centery)
            surface.blit(self.icon, icon_rect)
            label_rect = label_surf.get_rect(midleft=(icon_rect.right + 12, rect.centery))
            surface.blit(label_surf, label_rect)
        else:
            draw_text(surface, self.text, self.font, text_color, rect.center, shadow=False)

        if not self.enabled:
            dim = pygame.Surface(rect.size, pygame.SRCALPHA)
            dim.fill((5, 5, 8, 110))
            surface.blit(dim, rect.topleft)


class ToggleButton(Button):
    """A button whose label reflects an ON/OFF boolean state."""

    def __init__(self, rect, label_prefix: str, get_state: Callable[[], bool], on_click, **kwargs):
        self.label_prefix = label_prefix
        self.get_state = get_state
        super().__init__(rect, "", kwargs.pop("font"), on_click=on_click, **kwargs)
        self._refresh_label()

    def _refresh_label(self) -> None:
        state = "ON" if self.get_state() else "OFF"
        self.text = f"{self.label_prefix}: {state}"

    def draw(self, surface: pygame.Surface) -> None:
        self._refresh_label()
        super().draw(surface)


class Slider:
    """A horizontal, click-or-drag volume-style slider in the 0..1 range."""

    def __init__(
        self,
        rect: tuple[int, int, int, int],
        value: float = 0.5,
        on_change: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.rect = pygame.Rect(rect)
        self.value = clamp01(value)
        self.dragging = False
        self.on_change = on_change

    def handle_event(self, event: pygame.event.Event, mouse_pos_override=None) -> None:
        pos = mouse_pos_override if mouse_pos_override is not None else getattr(event, "pos", None)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and pos is not None:
            handle_area = self.rect.inflate(0, 16)
            if handle_area.collidepoint(pos):
                self.dragging = True
                self._set_from_x(pos[0])
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging and pos is not None:
            self._set_from_x(pos[0])

    def _set_from_x(self, x: float) -> None:
        t = clamp01((x - self.rect.left) / self.rect.width)
        self.value = t
        if self.on_change:
            self.on_change(t)

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, (50, 55, 74), self.rect, border_radius=6)
        fill_w = int(self.rect.width * self.value)
        if fill_w > 0:
            fill_rect = pygame.Rect(self.rect.left, self.rect.top, fill_w, self.rect.height)
            pygame.draw.rect(surface, cfg.COLOR_ACCENT, fill_rect, border_radius=6)
        knob_x = self.rect.left + fill_w
        knob_radius = self.rect.height
        pygame.draw.circle(surface, (0, 0, 0, 90), (knob_x, self.rect.centery + 2), knob_radius)
        pygame.draw.circle(surface, cfg.COLOR_TEXT, (knob_x, self.rect.centery), knob_radius)
