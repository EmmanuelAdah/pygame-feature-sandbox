"""
SURVIVAL PONG
=============
A 2D arcade game inspired by Pong, but instead of scoring points, both
players share a single health pool and must cooperate to keep the ball
away from the left and right walls for as long as possible.

Controls:
    Left Paddle  -> W (up) / S (down)
    Right Paddle -> UP ARROW / DOWN ARROW
    R            -> Restart after Game Over
    ESC / Q      -> Quit

Run:
    pip install pygame
    python survival_pong.py
"""

import sys
import random
import pygame

# --------------------------------------------------------------------------
# CONFIGURATION / CONSTANTS
# --------------------------------------------------------------------------

SCREEN_WIDTH = 900
SCREEN_HEIGHT = 600
FPS = 60

# Colors (minimalist, high-contrast neon-on-dark theme)
COLOR_BG = (10, 10, 18)
COLOR_WALL = (40, 40, 60)
COLOR_DAMAGE_ZONE = (60, 15, 25)
COLOR_PADDLE_LEFT = (0, 255, 200)      # neon cyan
COLOR_PADDLE_RIGHT = (255, 60, 220)    # neon magenta
COLOR_BALL = (255, 255, 90)            # neon yellow
COLOR_TEXT = (240, 240, 240)
COLOR_HEALTH_FULL = (60, 220, 100)
COLOR_HEALTH_LOW = (220, 60, 60)
COLOR_CENTER_LINE = (35, 35, 50)

# Arena / wall thickness (top & bottom are solid bouncing walls)
WALL_THICKNESS = 10
DAMAGE_ZONE_WIDTH = 14  # visual thickness of the left/right "danger" strips

# Paddle settings
PADDLE_WIDTH = 16
PADDLE_HEIGHT = 110
PADDLE_SPEED = 7
PADDLE_INSET = 40  # distance from the side wall

# Ball settings
BALL_SIZE = 16
BALL_BASE_SPEED = 6.0
BALL_SPEED_INCREASE = 1.05  # +5% speed per successful paddle bounce
BALL_MAX_SPEED = 22.0

# Health / lives
STARTING_HEALTH = 5
RESET_PAUSE_MS = 1000  # 1 second pause after a damage event

# Fonts (initialized after pygame.init())
FONT_LARGE = None
FONT_MEDIUM = None
FONT_SMALL = None


# --------------------------------------------------------------------------
# ENTITY CLASSES
# --------------------------------------------------------------------------

class Paddle:
    """A vertically-moving rectangle controlled by a player."""

    def __init__(self, x, color, up_key, down_key):
        self.width = PADDLE_WIDTH
        self.height = PADDLE_HEIGHT
        self.x = x
        self.y = SCREEN_HEIGHT // 2 - self.height // 2
        self.color = color
        self.up_key = up_key
        self.down_key = down_key
        self.speed = PADDLE_SPEED

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)

    def handle_input(self, keys):
        """Move the paddle based on currently-held keys."""
        if keys[self.up_key]:
            self.y -= self.speed
        if keys[self.down_key]:
            self.y += self.speed

        # Clamp so the paddle never passes through top/bottom walls
        min_y = WALL_THICKNESS
        max_y = SCREEN_HEIGHT - WALL_THICKNESS - self.height
        self.y = max(min_y, min(self.y, max_y))

    def draw(self, surface):
        rect = self.rect
        pygame.draw.rect(surface, self.color, rect, border_radius=4)
        # subtle glow effect using a translucent outline
        glow_rect = rect.inflate(6, 6)
        glow_surf = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(glow_surf, (*self.color, 60), glow_surf.get_rect(), border_radius=6)
        surface.blit(glow_surf, glow_rect.topleft)


class Ball:
    """The bouncing ball with simple velocity-based physics."""

    def __init__(self):
        self.size = BALL_SIZE
        self.reset()

    def reset(self, direction=None):
        """Place the ball in the center with a fresh randomized trajectory."""
        self.x = SCREEN_WIDTH / 2 - self.size / 2
        self.y = SCREEN_HEIGHT / 2 - self.size / 2

        if direction is None:
            direction = random.choice([-1, 1])

        angle_variance = random.uniform(-0.35, 0.35)  # radians-ish tilt
        self.vx = direction * BALL_BASE_SPEED
        self.vy = BALL_BASE_SPEED * angle_variance
        self.speed = BALL_BASE_SPEED

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.size, self.size)

    def update(self):
        self.x += self.vx
        self.y += self.vy

    def bounce_off_horizontal_wall(self):
        """Reverse Y velocity when hitting top/bottom walls."""
        self.vy *= -1

    def bounce_off_paddle(self, paddle: "Paddle", is_left_paddle: bool):
        """
        Reverse X velocity and apply deflection based on where the ball
        struck the paddle (center vs. edges), then speed the ball up.
        """
        # Where did the ball hit, relative to the paddle's center? (-1..1)
        paddle_center = paddle.y + paddle.height / 2
        ball_center = self.y + self.size / 2
        offset = (ball_center - paddle_center) / (paddle.height / 2)
        offset = max(-1.0, min(1.0, offset))

        # Reverse X direction (always send it back across the arena)
        direction = 1 if is_left_paddle else -1
        self.speed = min(self.speed * BALL_SPEED_INCREASE, BALL_MAX_SPEED)
        self.vx = direction * self.speed

        # Deflection: edges produce a steeper vertical angle than center hits
        max_deflection = self.speed * 0.9
        self.vy = offset * max_deflection

        # Nudge the ball outside the paddle so it doesn't get stuck
        if is_left_paddle:
            self.x = paddle.rect.right + 1
        else:
            self.x = paddle.rect.left - self.size - 1

    def draw(self, surface):
        rect = self.rect
        pygame.draw.rect(surface, COLOR_BALL, rect, border_radius=4)
        glow_surf = pygame.Surface((rect.width + 10, rect.height + 10), pygame.SRCALPHA)
        pygame.draw.rect(glow_surf, (*COLOR_BALL, 70), glow_surf.get_rect(), border_radius=6)
        surface.blit(glow_surf, (rect.x - 5, rect.y - 5))


# --------------------------------------------------------------------------
# GAME STATE
# --------------------------------------------------------------------------

class GameState:
    """Holds all mutable game state and high-level state transitions."""

    def __init__(self):
        self.left_paddle = Paddle(PADDLE_INSET, COLOR_PADDLE_LEFT, pygame.K_w, pygame.K_s)
        self.right_paddle = Paddle(
            SCREEN_WIDTH - PADDLE_INSET - PADDLE_WIDTH,
            COLOR_PADDLE_RIGHT,
            pygame.K_UP,
            pygame.K_DOWN,
        )
        self.ball = Ball()
        self.health = STARTING_HEALTH
        self.bounce_count = 0
        self.start_ticks = pygame.time.get_ticks()
        self.time_survived_ms = 0

        self.game_over = False
        self.paused_until = 0  # timestamp (ms) until which the game is paused
        self.is_paused = False
        self.last_damage_side = None  # "left" or "right", used for flash effect
        self.flash_timer = 0

    def reset_game(self):
        self.__init__()

    # ---------------------------------------------------------------
    # Update
    # ---------------------------------------------------------------
    def update(self, keys, now_ms):
        if self.game_over:
            return

        # Handle the brief pause after a damage event
        if self.is_paused:
            if now_ms >= self.paused_until:
                self.is_paused = False
                self.ball.reset()
            else:
                return  # freeze everything else while paused

        # Track survival time
        self.time_survived_ms = now_ms - self.start_ticks

        # Input
        self.left_paddle.handle_input(keys)
        self.right_paddle.handle_input(keys)

        # Physics
        self.ball.update()
        self.handle_collisions(now_ms)

    # ---------------------------------------------------------------
    # Collision Detection
    # ---------------------------------------------------------------
    def handle_collisions(self, now_ms):
        ball_rect = self.ball.rect

        # --- Top / Bottom walls: perfect bounce ---
        if ball_rect.top <= WALL_THICKNESS:
            self.ball.y = WALL_THICKNESS
            self.ball.bounce_off_horizontal_wall()
        elif ball_rect.bottom >= SCREEN_HEIGHT - WALL_THICKNESS:
            self.ball.y = SCREEN_HEIGHT - WALL_THICKNESS - self.ball.size
            self.ball.bounce_off_horizontal_wall()

        # --- Paddle collisions ---
        ball_rect = self.ball.rect  # refresh after any Y correction
        if self.ball.vx < 0 and ball_rect.colliderect(self.left_paddle.rect):
            self.ball.bounce_off_paddle(self.left_paddle, is_left_paddle=True)
            self.bounce_count += 1
        elif self.ball.vx > 0 and ball_rect.colliderect(self.right_paddle.rect):
            self.ball.bounce_off_paddle(self.right_paddle, is_left_paddle=False)
            self.bounce_count += 1

        # --- Damage zones: left / right walls ---
        ball_rect = self.ball.rect
        if ball_rect.left <= 0:
            self.trigger_damage_event("left", now_ms)
        elif ball_rect.right >= SCREEN_WIDTH:
            self.trigger_damage_event("right", now_ms)

    def trigger_damage_event(self, side, now_ms):
        self.health -= 1
        self.last_damage_side = side
        self.flash_timer = now_ms + 300  # brief red flash duration

        # Freeze the ball where it is; reset will happen after the pause
        self.ball.vx = 0
        self.ball.vy = 0

        if self.health <= 0:
            self.health = 0
            self.game_over = True
        else:
            self.is_paused = True
            self.paused_until = now_ms + RESET_PAUSE_MS


# --------------------------------------------------------------------------
# RENDERING
# --------------------------------------------------------------------------

def draw_arena(surface):
    surface.fill(COLOR_BG)

    # Damage zone strips (left/right) - subtle warning color
    pygame.draw.rect(surface, COLOR_DAMAGE_ZONE, (0, 0, DAMAGE_ZONE_WIDTH, SCREEN_HEIGHT))
    pygame.draw.rect(
        surface, COLOR_DAMAGE_ZONE,
        (SCREEN_WIDTH - DAMAGE_ZONE_WIDTH, 0, DAMAGE_ZONE_WIDTH, SCREEN_HEIGHT)
    )

    # Top / bottom solid walls
    pygame.draw.rect(surface, COLOR_WALL, (0, 0, SCREEN_WIDTH, WALL_THICKNESS))
    pygame.draw.rect(surface, COLOR_WALL, (0, SCREEN_HEIGHT - WALL_THICKNESS, SCREEN_WIDTH, WALL_THICKNESS))

    # Center dashed line
    dash_height = 12
    gap = 10
    y = WALL_THICKNESS
    while y < SCREEN_HEIGHT - WALL_THICKNESS:
        pygame.draw.rect(surface, COLOR_CENTER_LINE, (SCREEN_WIDTH // 2 - 2, y, 4, dash_height))
        y += dash_height + gap


def draw_damage_flash(surface, state: GameState, now_ms):
    """Flash the screen edge briefly red when a damage event occurs."""
    if state.flash_timer > now_ms:
        alpha = int(150 * ((state.flash_timer - now_ms) / 300))
        flash_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        color = (255, 40, 40, alpha)
        if state.last_damage_side == "left":
            pygame.draw.rect(flash_surf, color, (0, 0, 60, SCREEN_HEIGHT))
        elif state.last_damage_side == "right":
            pygame.draw.rect(flash_surf, color, (SCREEN_WIDTH - 60, 0, 60, SCREEN_HEIGHT))
        surface.blit(flash_surf, (0, 0))


def draw_hud(surface, state: GameState):
    # --- Health display (hearts / blocks) ---
    label = FONT_SMALL.render("HEALTH", True, COLOR_TEXT)
    surface.blit(label, (20, 14))

    heart_size = 22
    heart_gap = 8
    start_x = 20
    start_y = 38
    for i in range(STARTING_HEALTH):
        rect = pygame.Rect(start_x + i * (heart_size + heart_gap), start_y, heart_size, heart_size)
        if i < state.health:
            ratio = state.health / STARTING_HEALTH
            color = COLOR_HEALTH_FULL if ratio > 0.4 else COLOR_HEALTH_LOW
            pygame.draw.rect(surface, color, rect, border_radius=4)
        else:
            pygame.draw.rect(surface, COLOR_WALL, rect, border_radius=4, width=2)

    # --- Time survived ---
    seconds = state.time_survived_ms // 1000
    minutes = seconds // 60
    seconds %= 60
    time_text = FONT_MEDIUM.render(f"Time: {minutes:02d}:{seconds:02d}", True, COLOR_TEXT)
    time_rect = time_text.get_rect(midtop=(SCREEN_WIDTH // 2, 14))
    surface.blit(time_text, time_rect)

    # --- Bounce counter (score) ---
    bounce_text = FONT_MEDIUM.render(f"Bounces: {state.bounce_count}", True, COLOR_TEXT)
    bounce_rect = bounce_text.get_rect(topright=(SCREEN_WIDTH - 20, 20))
    surface.blit(bounce_text, bounce_rect)

    # --- Controls reminder (bottom corners) ---
    left_hint = FONT_SMALL.render("W / S", True, COLOR_PADDLE_LEFT)
    surface.blit(left_hint, (20, SCREEN_HEIGHT - 30))
    right_hint = FONT_SMALL.render("UP / DOWN", True, COLOR_PADDLE_RIGHT)
    right_hint_rect = right_hint.get_rect(bottomright=(SCREEN_WIDTH - 20, SCREEN_HEIGHT - 10))
    surface.blit(right_hint, right_hint_rect)


def draw_pause_message(surface):
    text = FONT_MEDIUM.render("Ball incoming...", True, (255, 210, 90))
    rect = text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 60))
    surface.blit(text, rect)


def draw_game_over(surface, state: GameState, restart_button_rect):
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 190))
    surface.blit(overlay, (0, 0))

    title = FONT_LARGE.render("GAME OVER", True, (255, 80, 80))
    title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 120))
    surface.blit(title, title_rect)

    seconds = state.time_survived_ms // 1000
    minutes = seconds // 60
    seconds %= 60
    stats_text = FONT_MEDIUM.render(
        f"Survived: {minutes:02d}:{seconds:02d}   |   Bounces: {state.bounce_count}",
        True, COLOR_TEXT
    )
    stats_rect = stats_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 55))
    surface.blit(stats_text, stats_rect)

    # Restart button
    mouse_pos = pygame.mouse.get_pos()
    hovered = restart_button_rect.collidepoint(mouse_pos)
    button_color = (80, 220, 140) if hovered else (50, 180, 110)
    pygame.draw.rect(surface, button_color, restart_button_rect, border_radius=10)
    pygame.draw.rect(surface, COLOR_TEXT, restart_button_rect, width=2, border_radius=10)

    btn_text = FONT_MEDIUM.render("Restart", True, (10, 10, 18))
    btn_text_rect = btn_text.get_rect(center=restart_button_rect.center)
    surface.blit(btn_text, btn_text_rect)

    hint = FONT_SMALL.render("(or press R)", True, (170, 170, 180))
    hint_rect = hint.get_rect(center=(SCREEN_WIDTH // 2, restart_button_rect.bottom + 26))
    surface.blit(hint, hint_rect)


def draw_all(surface, state: GameState, now_ms, restart_button_rect):
    draw_arena(surface)

    state.left_paddle.draw(surface)
    state.right_paddle.draw(surface)
    state.ball.draw(surface)

    draw_hud(surface, state)
    draw_damage_flash(surface, state, now_ms)

    if state.is_paused and not state.game_over:
        draw_pause_message(surface)

    if state.game_over:
        draw_game_over(surface, state, restart_button_rect)


# --------------------------------------------------------------------------
# INPUT HANDLING
# --------------------------------------------------------------------------

def handle_events(state: GameState, restart_button_rect):
    """Process discrete events (quit, keydown, mouse clicks). Returns False to quit."""
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                return False
            if event.key == pygame.K_r and state.game_over:
                state.reset_game()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if state.game_over and restart_button_rect.collidepoint(event.pos):
                state.reset_game()

    return True


# --------------------------------------------------------------------------
# MAIN GAME LOOP
# --------------------------------------------------------------------------

def main():
    global FONT_LARGE, FONT_MEDIUM, FONT_SMALL

    pygame.init()
    pygame.display.set_caption("Survival Pong")
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()

    FONT_LARGE = pygame.font.SysFont("consolas", 56, bold=True)
    FONT_MEDIUM = pygame.font.SysFont("consolas", 28, bold=True)
    FONT_SMALL = pygame.font.SysFont("consolas", 18, bold=True)

    state = GameState()

    restart_button_rect = pygame.Rect(0, 0, 200, 56)
    restart_button_rect.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 40)

    running = True
    while running:
        now_ms = pygame.time.get_ticks()

        running = handle_events(state, restart_button_rect)

        keys = pygame.key.get_pressed()
        state.update(keys, now_ms)

        draw_all(screen, state, now_ms, restart_button_rect)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
