"""General-purpose helpers shared across the project."""

from __future__ import annotations

import pygame


def clamp01(t: float) -> float:
    return max(0.0, min(1.0, t))


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_out_cubic(t: float) -> float:
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def ease_in_out_quad(t: float) -> float:
    t = clamp01(t)
    return 2 * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 2) / 2


def ease_out_back(t: float, overshoot: float = 1.7) -> float:
    """Overshoots past 1.0 then settles - a springy 'pop' feel."""
    t = clamp01(t) - 1
    return 1 + (overshoot + 1) * (t ** 3) + overshoot * (t ** 2)


def ease_out_elastic(t: float) -> float:
    """A bouncy elastic settle, used sparingly for extra-playful pops."""
    import math

    t = clamp01(t)
    if t in (0.0, 1.0):
        return t
    c4 = (2 * math.pi) / 3
    return pow(2, -10 * t) * math.sin((t * 10 - 0.75) * c4) + 1


def scale_image_keep_aspect(
    image: pygame.Surface, max_width: int, max_height: int
) -> pygame.Surface:
    """Scale an image to fit within (max_width, max_height) without distortion."""
    src_w, src_h = image.get_size()
    if src_w == 0 or src_h == 0:
        return image
    scale = min(max_width / src_w, max_height / src_h)
    new_size = (max(1, int(src_w * scale)), max(1, int(src_h * scale)))
    return pygame.transform.smoothscale(image, new_size)


def vertical_gradient(size: tuple[int, int], top_color, bottom_color) -> pygame.Surface:
    """Build a simple top-to-bottom gradient surface."""
    surf = pygame.Surface(size)
    height = size[1]
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top_color[i] + (bottom_color[i] - top_color[i]) * t) for i in range(3))
        pygame.draw.line(surf, color, (0, y), (size[0], y))
    return surf


def radial_vignette(size: tuple[int, int], strength: int = 140) -> pygame.Surface:
    """A soft dark vignette overlay, precomputed once and cached by the caller."""
    surf = pygame.Surface(size, pygame.SRCALPHA)
    w, h = size
    cx, cy = w / 2, h / 2
    max_dist = (cx ** 2 + cy ** 2) ** 0.5
    # Downsample for performance, then scale up smoothly.
    small_w, small_h = max(2, w // 8), max(2, h // 8)
    small = pygame.Surface((small_w, small_h), pygame.SRCALPHA)
    for yy in range(small_h):
        for xx in range(small_w):
            px = xx / small_w * w
            py = yy / small_h * h
            dist = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
            t = clamp01(dist / max_dist)
            alpha = int(strength * (t ** 2))
            small.set_at((xx, yy), (0, 0, 0, alpha))
    return pygame.transform.smoothscale(small, size)


def draw_text(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    color,
    center: tuple[int, int],
    shadow: bool = True,
    shadow_color=(0, 0, 0),
    shadow_offset=(2, 3),
    shadow_alpha=130,
) -> pygame.Rect:
    """Render text centered at `center`, with an optional soft drop shadow."""
    if shadow:
        shadow_surf = font.render(text, True, shadow_color)
        shadow_surf.set_alpha(shadow_alpha)
        shadow_rect = shadow_surf.get_rect(
            center=(center[0] + shadow_offset[0], center[1] + shadow_offset[1])
        )
        surface.blit(shadow_surf, shadow_rect)
    surf = font.render(text, True, color)
    rect = surf.get_rect(center=center)
    surface.blit(surf, rect)
    return rect
