"""Window size, colours and tuning knobs."""

VIEW_W, VIEW_H = 960, 640
PANEL_W = 280
WIDTH, HEIGHT = VIEW_W + PANEL_W, VIEW_H
WORLD_W, WORLD_H = 2800, 2000
FPS = 60
TITLE = "Mini Shooter"
# Title-screen Exit in the browser returns here. The desktop app still closes.
ARCADE_URL = "https://meltedlamp.github.io/melted-arcade/"
MARGIN = 34
UPGRADE_EVERY = 100

MAX_HEARTS = 5
PLAYER_SPEED = 245
PLAYER_RADIUS = 15
DASH_SPEED = 640
DASH_TIME = 0.16
DASH_COOLDOWN = 0.82
FIRE_COOLDOWN = 0.14
PLAYER_BULLET_SPEED = 700
ENEMY_BULLET_SPEED = 255
HURT_TIME = 0.95

FLOOR = (20, 24, 34)
GRID = (32, 38, 52)
WALL = (28, 32, 44)
WALL_EDGE = (78, 92, 118)
CRATE = (118, 90, 66)
CRATE_DARK = (74, 54, 42)
CRATE_LIGHT = (168, 132, 90)
INK = (14, 16, 24)
TEXT = (236, 240, 248)
MUTED = (168, 176, 196)
GOLD = (255, 214, 120)
CYAN = (86, 214, 255)
AMBER = (255, 186, 84)

CRATES = (
    (180, 160, 120, 120),
    (520, 420, 160, 70),
    (980, 180, 90, 150),
    (1500, 220, 130, 90),
    (2000, 160, 110, 140),
    (2400, 400, 140, 80),
    (300, 780, 100, 160),
    (700, 980, 150, 70),
    (1100, 760, 80, 120),
    (1800, 820, 140, 80),
    (2300, 900, 100, 150),
    (400, 1400, 140, 80),
    (900, 1500, 90, 140),
    (1400, 1480, 160, 70),
    (1900, 1400, 120, 120),
    (2400, 1500, 130, 90),
    (1600, 1180, 90, 100),
    (600, 1600, 120, 80),
)
