"""
Centralized asset loading and caching.

Design goal (per project spec): the game must run out of the box with zero
external files, but should transparently pick up nicer, real artwork the
moment someone drops matching filenames into ``assets/images``. Every image
is therefore resolved through :meth:`AssetManager._load_or_generate`, which
prefers a real file on disk and only falls back to procedural generation
(stylized vector-style art with shading, gradients and shadows - not flat
primitives) when no file is found or the file fails to load.
"""

from __future__ import annotations

import math
import random

import pygame

from . import settings as cfg


class AssetManager:
    """Loads (or synthesizes) and caches every image used by the game."""

    def __init__(self) -> None:
        self.images: dict[str, pygame.Surface] = {}
        self._load_all()

    # ---- public API -------------------------------------------------

    def get(self, name: str) -> pygame.Surface:
        image = self.images.get(name)
        if image is None:
            print(f"Warning: requested unknown image '{name}'.")
            image = self._placeholder((256, 256))
            self.images[name] = image
        return image

    # ---- loading / fallback ------------------------------------------

    def _load_all(self) -> None:
        self.images["rock"] = self._load_or_generate(
            "rock.png", self._generate_rock, (460, 420)
        )
        self.images["paper"] = self._load_or_generate(
            "paper.png", self._generate_paper, (420, 460)
        )
        self.images["scissors"] = self._load_or_generate(
            "scissors.png", self._generate_scissors, (460, 460)
        )
        self.images["background"] = self._load_or_generate(
            "background.png", self._generate_background,
            (cfg.SCREEN_WIDTH, cfg.SCREEN_HEIGHT),
        )
        self.images["logo"] = self._load_or_generate(
            "logo.png", self._generate_logo, (820, 200)
        )

    def _load_or_generate(self, filename: str, generator, size: tuple[int, int]) -> pygame.Surface:
        path = cfg.IMAGES_DIR / filename
        if path.exists():
            try:
                return pygame.image.load(str(path)).convert_alpha()
            except pygame.error as exc:
                print(f"Warning: could not load '{path}' ({exc}). Using generated artwork instead.")
        try:
            return generator(*size)
        except Exception as exc:  # noqa: BLE001 - never let a missing asset crash the game
            print(f"Warning: failed to generate asset '{filename}' ({exc}). Using placeholder.")
            return self._placeholder(size)

    @staticmethod
    def _placeholder(size: tuple[int, int]) -> pygame.Surface:
        surf = pygame.Surface(size, pygame.SRCALPHA)
        surf.fill((90, 20, 20, 200))
        pygame.draw.line(surf, (255, 255, 255), (0, 0), size, 4)
        pygame.draw.line(surf, (255, 255, 255), (0, size[1]), (size[0], 0), 4)
        return surf

    # ---- procedural generators -----------------------------------------
    # These build stylized, shaded "game-icon" style art using layered
    # polygons, gradients and soft shadows rather than flat shapes.

    def _generate_rock(self, w: int, h: int) -> pygame.Surface:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        cx, cy = w // 2, int(h * 0.52)
        rng = random.Random(7)

        num_points = 16
        radius_base = min(w, h) * 0.34
        points = []
        for i in range(num_points):
            angle = (i / num_points) * 2 * math.pi
            wobble = 0.86 + 0.16 * math.sin(i * 2.3) + rng.uniform(-0.04, 0.04)
            r = radius_base * wobble
            points.append((cx + math.cos(angle) * r, cy + math.sin(angle) * r * 0.9))

        # Soft ground shadow beneath the rock.
        shadow_center = (cx, int(cy + radius_base * 0.95))
        shadow_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(
            shadow_surf, (0, 0, 0, 85),
            pygame.Rect(shadow_center[0] - radius_base, shadow_center[1] - radius_base * 0.28,
                        radius_base * 2, radius_base * 0.56),
        )
        surf.blit(shadow_surf, (0, 0))

        # Build the shaded rock body on its own layer, then clip it to the
        # polygon silhouette using an alpha-multiply mask so highlights and
        # shadows never spill outside the rock's outline.
        base_color = (118, 112, 104)
        shade_layer = pygame.Surface((w, h), pygame.SRCALPHA)
        shade_layer.fill((*base_color, 255))

        shadow_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(
            shadow_overlay, (0, 0, 0, 70),
            pygame.Rect(int(cx - radius_base * 0.3), int(cy + radius_base * 0.1),
                        int(radius_base * 1.6), int(radius_base * 1.1)),
        )
        shade_layer.blit(shadow_overlay, (0, 0))

        highlight_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(
            highlight_overlay, (255, 255, 255, 60),
            pygame.Rect(int(cx - radius_base * 0.95), int(cy - radius_base * 1.0),
                        int(radius_base * 1.15), int(radius_base * 0.85)),
        )
        shade_layer.blit(highlight_overlay, (0, 0))

        # Interior crack lines (kept well inside the silhouette so clipping
        # doesn't need to trim them).
        for _ in range(6):
            anchor_angle = rng.uniform(0, 2 * math.pi)
            anchor_r = radius_base * rng.uniform(0.15, 0.55)
            p1 = (cx + math.cos(anchor_angle) * anchor_r, cy + math.sin(anchor_angle) * anchor_r * 0.9)
            length = rng.uniform(16, 34)
            ang = anchor_angle + rng.uniform(-0.6, 0.6)
            p2 = (p1[0] + math.cos(ang) * length, p1[1] + math.sin(ang) * length)
            pygame.draw.line(shade_layer, (70, 66, 60, 150), p1, p2, 2)

        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255), points)
        mask.blit(shade_layer, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        surf.blit(mask, (0, 0))

        # Rim light outline drawn last, directly on the silhouette edge.
        pygame.draw.polygon(surf, (205, 200, 190, 130), points, 3)
        return surf

    def _generate_paper(self, w: int, h: int) -> pygame.Surface:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        margin = int(min(w, h) * 0.10)
        sheet_rect = pygame.Rect(margin, margin, w - margin * 2, h - margin * 2)

        # Drop shadow.
        shadow_rect = sheet_rect.move(10, 14)
        shadow_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(shadow_surf, (0, 0, 0, 90), shadow_rect, border_radius=10)
        surf.blit(shadow_surf, (0, 0))

        # Paper body with a very slight parallelogram skew for perspective.
        skew = int(sheet_rect.width * 0.03)
        pts = [
            (sheet_rect.left + skew, sheet_rect.top),
            (sheet_rect.right, sheet_rect.top + skew // 2),
            (sheet_rect.right - skew, sheet_rect.bottom),
            (sheet_rect.left, sheet_rect.bottom - skew // 2),
        ]
        pygame.draw.polygon(surf, (245, 244, 238), pts)
        pygame.draw.polygon(surf, (205, 202, 190), pts, 2)

        # Folded corner (top-right dog-ear).
        fold_size = int(sheet_rect.width * 0.22)
        corner = (sheet_rect.right - skew, sheet_rect.top + skew // 2)
        fold_pts = [
            (corner[0] - fold_size, corner[1]),
            corner,
            (corner[0], corner[1] + fold_size),
        ]
        pygame.draw.polygon(surf, (222, 220, 208), fold_pts)
        pygame.draw.polygon(surf, (190, 187, 176), fold_pts, 2)

        # Faint horizontal "text" lines for texture.
        line_color = (215, 213, 202)
        for i in range(6):
            y = sheet_rect.top + int(sheet_rect.height * (0.22 + i * 0.115))
            x0 = sheet_rect.left + int(sheet_rect.width * 0.14)
            x1 = sheet_rect.right - int(sheet_rect.width * (0.20 if i % 2 else 0.30))
            if y < corner[1] - fold_size * 0.3 or x1 < corner[0] - fold_size:
                pygame.draw.line(surf, line_color, (x0, y), (x1, y), 3)

        # Soft highlight along the top-left edge.
        highlight_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.line(
            highlight_surf, (255, 255, 255, 90),
            (sheet_rect.left + 6, sheet_rect.top + 10),
            (sheet_rect.left + 6, sheet_rect.bottom - 10), 6,
        )
        surf.blit(highlight_surf, (0, 0))
        return surf

    def _generate_scissors(self, w: int, h: int) -> pygame.Surface:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pivot = (w // 2, int(h * 0.40))
        blade_len = w * 0.40
        blade_w = h * 0.16

        def blade_surface(length: float, width: float) -> pygame.Surface:
            bs = pygame.Surface((int(length) + 6, int(width) + 6), pygame.SRCALPHA)
            pts = [
                (3, width / 2 + 3),
                (length * 0.62 + 3, width * 0.16 + 3),
                (length + 3, width * 0.10 + 3),
                (length * 0.62 + 3, width * 0.84 + 3),
            ]
            # shadow pass
            shadow_pts = [(x + 3, y + 5) for x, y in pts]
            pygame.draw.polygon(bs, (0, 0, 0, 70), shadow_pts)
            # metallic body
            pygame.draw.polygon(bs, (222, 226, 232, 255), pts)
            pygame.draw.polygon(bs, (140, 146, 156, 255), pts, 2)
            # bright streak highlight
            pygame.draw.line(
                bs, (255, 255, 255, 200),
                (length * 0.10 + 3, width * 0.30 + 3),
                (length * 0.78 + 3, width * 0.24 + 3), 3,
            )
            return bs

        blade = blade_surface(blade_len, blade_w)

        # Two handle "rings" (drawn as thick circle outlines, colored plastic)
        # and two blades, mirrored left/right to form an open "X" shape.
        handle_r = int(h * 0.15)
        arm_specs = [
            {"blade_angle": 30, "handle_offset": (-handle_r * 1.2, handle_r * 1.6),
             "color": (210, 70, 80)},
            {"blade_angle": -30, "handle_offset": (handle_r * 1.2, handle_r * 1.6),
             "color": (60, 130, 210)},
        ]

        for spec in arm_specs:
            handle_center = (pivot[0] + spec["handle_offset"][0], pivot[1] + spec["handle_offset"][1])

            # Short connecting arm from pivot to handle.
            pygame.draw.line(surf, (90, 92, 98), pivot, handle_center, max(6, int(h * 0.045)))

            # Handle ring (soft shadow first, then colored outline ring).
            shadow_center = (handle_center[0] + 3, handle_center[1] + 4)
            pygame.draw.circle(surf, (0, 0, 0, 80), shadow_center, handle_r + 2, 0)
            pygame.draw.circle(surf, spec["color"], handle_center, handle_r, max(7, int(handle_r * 0.4)))

            # Blade rotated outward/upward from the pivot, mirrored per side.
            rotated = pygame.transform.rotate(blade, spec["blade_angle"])
            blade_rect = rotated.get_rect()
            blade_rect.midleft = (pivot[0] - 6, pivot[1])
            surf.blit(rotated, blade_rect)

        # Pivot bolt.
        pygame.draw.circle(surf, (0, 0, 0, 90), (pivot[0] + 2, pivot[1] + 3), int(h * 0.045))
        pygame.draw.circle(surf, (235, 200, 90), pivot, int(h * 0.045))
        pygame.draw.circle(surf, (120, 100, 40), pivot, int(h * 0.045), 2)

        return surf

    def _generate_background(self, w: int, h: int) -> pygame.Surface:
        surf = pygame.Surface((w, h))
        top = cfg.COLOR_BG_TOP
        bottom = cfg.COLOR_BG_BOTTOM
        for y in range(h):
            t = y / h
            color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            pygame.draw.line(surf, color, (0, y), (w, y))

        rng = random.Random(11)
        # Soft diagonal light rays.
        ray_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for i in range(5):
            x = int(w * (0.1 + i * 0.22))
            pts = [(x, 0), (x + 160, 0), (x - 260, h), (x - 460, h)]
            pygame.draw.polygon(ray_surf, (255, 255, 255, 10), pts)
        surf.blit(ray_surf, (0, 0))

        # Scattered soft "bokeh" circles for ambient depth.
        bokeh_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        palette = [cfg.COLOR_ACCENT, cfg.COLOR_GOLD, (140, 110, 220)]
        for _ in range(26):
            x = rng.uniform(0, w)
            y = rng.uniform(0, h)
            r = rng.uniform(30, 110)
            color = rng.choice(palette)
            alpha = rng.randint(6, 16)
            pygame.draw.circle(bokeh_surf, (*color, alpha), (int(x), int(y)), int(r))
        surf.blit(bokeh_surf, (0, 0))

        # Subtle grid of thin lines toward the bottom for an "arena floor" feel.
        floor_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        floor_top = int(h * 0.78)
        for gx in range(0, w + 1, 64):
            pygame.draw.line(floor_surf, (255, 255, 255, 8), (gx, floor_top), (gx, h))
        for gy in range(floor_top, h + 1, 40):
            pygame.draw.line(floor_surf, (255, 255, 255, 8), (0, gy), (w, gy))
        surf.blit(floor_surf, (0, 0))

        return surf

    def _generate_logo(self, w: int, h: int) -> pygame.Surface:
        text = "ROCK  •  PAPER  •  SCISSORS"
        font_size = 66
        font_title = pygame.font.SysFont("georgia", font_size, bold=True)

        # Auto-fit: shrink the font until the rendered text comfortably fits
        # the requested canvas width, so nothing gets clipped.
        padding_x = 40
        while font_title.size(text)[0] > (w - padding_x) and font_size > 24:
            font_size -= 2
            font_title = pygame.font.SysFont("georgia", font_size, bold=True)

        surf = pygame.Surface((w, h), pygame.SRCALPHA)

        shadow = font_title.render(text, True, (0, 0, 0))
        shadow.set_alpha(140)
        shadow_rect = shadow.get_rect(center=(w // 2 + 4, h // 2 + 6))
        surf.blit(shadow, shadow_rect)

        glow = font_title.render(text, True, cfg.COLOR_ACCENT)
        glow.set_alpha(70)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            glow_rect = glow.get_rect(center=(w // 2 + dx, h // 2 + dy))
            surf.blit(glow, glow_rect)

        title = font_title.render(text, True, cfg.COLOR_TEXT)
        title_rect = title.get_rect(center=(w // 2, h // 2))
        surf.blit(title, title_rect)

        underline_y = title_rect.bottom + 14
        pygame.draw.line(
            surf, cfg.COLOR_GOLD,
            (title_rect.left + 20, underline_y), (title_rect.right - 20, underline_y), 3,
        )
        return surf
