"""Arena loop: waves, collisions, menus and the main draw."""

import asyncio
import math
import random
import sys

import pygame

from .actors import (
    Bullet, Enemy, Heart, Player, circle_hits_rect, draw_heart, push_circle_out_of_rect,
)
from .audio import Audio
from .fx import Floater, Particle, burst, ring
from .maps import MAPS
from .scores import read_high_score, read_map_open, write_high_score, write_map_open
from .settings import (
    AMBER, CYAN, DASH_COOLDOWN, FIRE_COOLDOWN, FPS, GOLD, HEIGHT, INK, MARGIN, MAX_HEARTS, MUTED,
    ARCADE_URL, PANEL_W, PLAYER_BULLET_SPEED, TEXT, TITLE, UPGRADE_EVERY, VIEW_H, VIEW_W, WALL, WIDTH, WORLD_H,
    WORLD_W,
)

UPGRADES = (
    ("rapid", "RAPID", "Shoot faster", (86, 214, 255)),
    ("spread", "SPREAD", "Fire a fan of shots", (186, 126, 255)),
    ("heavy", "HEAVY", "Harder, bigger hits", (255, 186, 84)),
    ("pierce", "PIERCE", "Shots pierce through", (130, 230, 150)),
)
UPGRADE_BY_KEY = {item[0]: item for item in UPGRADES}


def _ui_font(size, bold=False):
    """Segoe UI on the desktop. The browser build has no system fonts."""
    if sys.platform == "emscripten":
        return pygame.font.Font(None, size)
    return pygame.font.SysFont("segoeui", size, bold=bold)


class Game:
    def __init__(self, *, headless=False):
        self.headless = headless
        try:
            pre_init = getattr(pygame.mixer, "pre_init", None)
            if pre_init is not None:
                if sys.platform == "emscripten":
                    pre_init(44100, -16, 2, 4096)
                else:
                    pre_init(44100, -16, 1, 512)
        except Exception:
            pass
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.map_open = read_map_open(default=False)
        self.apply_window()
        self.world = pygame.Surface((WORLD_W, WORLD_H))
        self.clock = pygame.time.Clock()
        self.font = _ui_font(28)
        self.small = _ui_font(18)
        self.big = _ui_font(64, bold=True)
        self.button_font = _ui_font(26, bold=True)
        self.audio = Audio()
        self.arena = pygame.Rect(MARGIN, MARGIN, WORLD_W - MARGIN * 2, WORLD_H - MARGIN * 2)
        self.map_index = 0
        self.apply_map()
        rng = random.Random(4)
        self.scuffs = [
            (rng.randint(self.arena.left + 20, self.arena.right - 20),
             rng.randint(self.arena.top + 20, self.arena.bottom - 20),
             rng.randint(16, 40))
            for _ in range(56)
        ]
        self.shade = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
        self.shade.fill((6, 8, 14, 188))
        self.hurt_tint = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
        self.hurt_tint.fill((255, 36, 48, 55))
        self.high = read_high_score()
        self.running = True
        self.clicked = False
        self.time = 0.0
        self.offset = (0, 0)
        self.state = "start"
        self.decor = [
            Enemy("brute", (1320, 1240)),
            Enemy("grunt", (1780, 800)),
            Enemy("shooter", (1760, 1220)),
        ]
        for enemy in self.decor:
            enemy.spawn = 0
        self.preview = Player((1060, 1200))
        self.reset_run()

    def reset_run(self):
        self.player = Player((WORLD_W / 2, WORLD_H / 2))
        self.enemies = []
        self.bullets = []
        self.hearts = []
        self.particles = []
        self.floaters = []
        self.queue = []
        self.wave = 1
        self.banner = 1.2
        self.score = 0
        self.new_best = False
        self.shake = 0.0
        self.hitstop = 0.0
        self.death_t = 0.0
        self.dust_cd = 0.0
        self.mods = {"rapid": 0, "spread": 0, "heavy": 0, "pierce": 0}
        self.upgrade_at = UPGRADE_EVERY
        self.pending_upgrades = 0
        self.offers = []

    async def run(self):
        while self.running:
            dt = min(0.05, self.clock.tick(FPS) / 1000)
            self.clicked = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.remember_score()
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    self.on_key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.clicked = True
            self.time += dt
            self.offset = self.compute_offset()
            self.update(dt)
            self.draw()
            await asyncio.sleep(0)
        pygame.quit()

    def on_key(self, key):
        if key == pygame.K_m:
            self.audio.toggle()
            return
        if key == pygame.K_TAB:
            self.toggle_map()
            return
        if self.state == "upgrade" and key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_KP1, pygame.K_KP2, pygame.K_KP3):
            picked = {pygame.K_1: 0, pygame.K_KP1: 0, pygame.K_2: 1, pygame.K_KP2: 1, pygame.K_3: 2, pygame.K_KP3: 2}
            self.choose_upgrade(picked[key])
            return
        if key == pygame.K_ESCAPE:
            if self.state == "start":
                self.leave()
            elif self.state == "play":
                self.state = "pause"
            elif self.state == "pause":
                self.state = "play"
                self.player.fire_cd = 0.15
            elif self.state == "over":
                self.show_title()
        elif key in (pygame.K_RETURN, pygame.K_SPACE) and self.state in ("start", "over"):
            self.begin()

    def begin(self):
        self.reset_run()
        self.apply_map()
        self.state = "play"
        self.audio.set_bed(self.theme["id"])

    def leave(self):
        """Close the desktop window. In the browser, return to the arcade."""
        if sys.platform != "emscripten":
            self.running = False
            return
        import platform

        platform.window.location.href = ARCADE_URL

    def show_title(self):
        self.remember_score()
        self.state = "start"
        self.audio.set_bed(None)

    def apply_map(self):
        self.theme = MAPS[self.map_index]
        self.crates = [pygame.Rect(rect) for rect in self.theme["crates"]]
        self.hazards = [
            {"pos": pygame.Vector2(x, y), "radius": radius}
            for x, y, radius in self.theme["hazards"]
        ]
        pad = 118
        corners = (
            (self.arena.left + pad, self.arena.top + pad),
            (self.arena.right - pad, self.arena.top + pad),
            (self.arena.left + pad, self.arena.bottom - pad),
            (self.arena.right - pad, self.arena.bottom - pad),
        )
        self.secrets = [
            {"pos": pygame.Vector2(x, y), "name": name, "woken": False}
            for (x, y), name in zip(corners, self.theme["bosses"])
        ]

    def compute_offset(self):
        if self.state not in ("play", "pause") or self.shake < 0.3:
            return (0, 0)
        angle = random.random() * math.tau
        return (math.cos(angle) * self.shake, math.sin(angle) * self.shake)

    def update(self, dt):
        if self.clicked and self.map_toggle_rect().collidepoint(pygame.mouse.get_pos()):
            self.toggle_map()
            self.clicked = False
        if self.state == "start":
            self.update_title(dt)
        elif self.state == "play":
            self.update_play(dt)
        self.shake *= math.exp(-6 * dt)

    def update_title(self, dt):
        mouse = self.mouse_world()
        for enemy in self.decor:
            enemy.lived += dt
            enemy.walk += dt * 5
            aim = mouse - enemy.pos
            if aim.length_squared() > 1:
                enemy.angle = math.atan2(aim.y, aim.x)
        aim = mouse - self.preview.pos
        self.preview.lived += dt
        self.preview.walk += dt * 6
        self.preview.face(aim, dt)

    def update_play(self, dt):
        if self.hitstop > 0:
            self.hitstop = max(0.0, self.hitstop - dt)
            self.update_fx(dt * 0.25)
            return
        keys = pygame.key.get_pressed()
        move = pygame.Vector2(
            float((keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])),
            float((keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])),
        )
        mouse = self.mouse_world()
        pointer = pygame.mouse.get_pos()
        want_fire = (
            pygame.mouse.get_pressed()[0]
            and pointer[0] < VIEW_W
            and not self.map_toggle_rect().collidepoint(pointer)
        )
        want_dash = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        if self.player.alive:
            self.sync_gun()
            was_dashing = self.player.dash_t > 0
            cooldown, damage, pierce, speed, radius, color = self.gun_stats()
            bullet, casing = self.player.update(
                dt, move, mouse - self.player.pos, want_fire, want_dash,
                cooldown, speed, damage, pierce, radius, color, self.move_scale(),
            )
            self.keep_inside(self.player.pos, self.player.radius)
            self.update_secrets()
            self.touch_hazards()
            if bullet is not None:
                self.launch_bullets(bullet)
                origin, velocity = casing
                self.particles.append(Particle(origin, velocity, 0.35, AMBER, 2, gravity=420, shape="shell"))
                self.audio.play("shoot")
            if self.player.dash_t > 0 and not was_dashing:
                self.audio.play("dash")
            if self.player.vel.length() > 80:
                self.dust_cd -= dt
                if self.dust_cd <= 0:
                    self.dust_cd = 0.06
                    self.particles.append(Particle(
                        self.player.pos + pygame.Vector2(0, 8),
                        pygame.Vector2(random.uniform(-18, 18), random.uniform(-10, 10)),
                        0.28, (78, 86, 104), 3,
                    ))
        else:
            self.death_t -= dt

        if self.player.alive:
            self.update_waves(dt)
            self.update_enemies(dt)
        self.update_bullets(dt)
        self.update_hearts(dt)
        self.update_fx(dt)
        if not self.player.alive and self.death_t <= 0:
            self.state = "over"
            self.audio.set_bed(None)
        else:
            self.maybe_open_upgrade()

    def update_waves(self, dt):
        if self.banner > 0:
            self.banner = max(0.0, self.banner - dt)
            if self.banner == 0.0:
                self.queue = [[0.28, kind] for kind in self.wave_kinds(self.wave)]
                if self.queue:
                    self.queue[0][0] = 0.08
                self.audio.play("wave")
            return
        if self.queue:
            self.queue[0][0] -= dt
            if self.queue[0][0] <= 0:
                self.spawn_enemy(self.queue.pop(0)[1])
            return
        if not self.enemies:
            bonus = 15 * self.wave
            self.add_score(bonus)
            self.popup(self.player.pos + pygame.Vector2(0, -28), f"+{bonus}", GOLD)
            self.wave += 1
            self.banner = 1.15

    def wave_kinds(self, wave):
        total = min(12, 2 + wave)
        style = self.theme["wave"]
        if style == "heavy":
            brutes = 1 if wave >= 2 else 0
            if wave >= 3 and wave % 3 == 0:
                brutes += 1
            shooters = 0 if wave == 1 else max(0, wave // 3)
        elif style == "ranged":
            brutes = 1 if wave >= 4 and wave % 4 == 0 else 0
            shooters = 0 if wave == 1 else min(6, 1 + wave // 2)
        else:
            brutes = 2 if wave >= 9 and wave % 3 == 0 else (1 if wave >= 3 and wave % 3 == 0 else 0)
            shooters = 0 if wave == 1 else min(5, wave // 2)
        grunts = max(1, total - brutes - shooters)
        return ["brute"] * brutes + ["shooter"] * shooters + ["grunt"] * grunts

    def spawn_enemy(self, kind, pos=None):
        enemy = Enemy(kind, pos or self.spawn_point())
        enemy.speed *= self.theme["pace"]
        self.enemies.append(enemy)
        ring(self.particles, enemy.pos, enemy.color, 8)
        return enemy

    def spawn_point(self):
        for _ in range(30):
            angle = random.random() * math.tau
            dist = random.uniform(640, 980)
            pos = self.player.pos + pygame.Vector2(math.cos(angle) * dist, math.sin(angle) * dist)
            pos.x = min(max(pos.x, self.arena.left + 40), self.arena.right - 40)
            pos.y = min(max(pos.y, self.arena.top + 40), self.arena.bottom - 40)
            if pos.distance_to(self.player.pos) < 560:
                continue
            if any(circle_hits_rect(pos, 24, crate) for crate in self.crates):
                continue
            return pos
        return pygame.Vector2(self.arena.left + 40, self.arena.top + 40)

    def update_enemies(self, dt):
        alive = []
        for enemy in self.enemies:
            shot = enemy.update(dt, self.player, self.crates)
            if isinstance(shot, list):
                self.bullets.extend(shot)
            elif shot is not None:
                self.bullets.append(shot)
            if enemy.alive or enemy.dying > 0:
                if enemy.alive:
                    self.keep_inside(enemy.pos, enemy.radius)
                alive.append(enemy)
        self.enemies = alive
        for i, first in enumerate(self.enemies):
            if not first.alive:
                continue
            for second in self.enemies[i + 1:]:
                if not second.alive:
                    continue
                delta = first.pos - second.pos
                dist = delta.length()
                need = first.radius + second.radius
                if 0 < dist < need:
                    push = delta / dist * (need - dist) * 0.5
                    first.pos += push
                    second.pos -= push
        for enemy in self.enemies:
            if enemy.alive:
                self.keep_inside(enemy.pos, enemy.radius)
        for enemy in self.enemies:
            if not enemy.alive or enemy.spawn > 0 or not self.player.alive:
                continue
            reach = enemy.radius + self.player.radius - 2
            if enemy.pos.distance_to(self.player.pos) < reach:
                self.hurt_player(enemy.pos)

    def update_bullets(self, dt):
        kept = []
        for bullet in self.bullets:
            speed = bullet.vel.length()
            steps = max(1, int(speed * dt / 10))
            points = bullet.advance(dt, steps)
            if bullet.life <= 0:
                continue
            dead = False
            for point in points:
                bullet.pos = point
                if not self.arena.collidepoint(point) or any(circle_hits_rect(point, bullet.radius, c) for c in self.crates):
                    burst(self.particles, point, (255, 220, 170), 6, 90, 0.25, 3)
                    dead = True
                    break
                if bullet.friendly:
                    for enemy in self.enemies:
                        if not enemy.alive or id(enemy) in bullet.hit_ids:
                            continue
                        if point.distance_to(enemy.pos) < enemy.radius + bullet.radius:
                            bullet.hit_ids.add(id(enemy))
                            self.damage_enemy(enemy, point, bullet.damage)
                            if bullet.pierce > 0:
                                bullet.pierce -= 1
                            else:
                                dead = True
                            break
                elif self.player.alive and point.distance_to(self.player.pos) < self.player.radius + bullet.radius:
                    self.hurt_player(point)
                    burst(self.particles, point, (255, 140, 110), 5, 80, 0.2, 3)
                    dead = True
                if dead:
                    break
            if not dead:
                kept.append(bullet)
        self.bullets = kept

    def update_hearts(self, dt):
        kept = []
        for heart in self.hearts:
            heart.update(dt)
            reach = heart.radius + self.player.radius
            if self.player.alive and heart.pos.distance_to(self.player.pos) <= reach:
                if self.player.hearts < MAX_HEARTS:
                    self.player.hearts += 1
                    self.popup(heart.pos, "+1", (255, 150, 170))
                else:
                    self.add_score(50)
                    self.popup(heart.pos, "+50", GOLD)
                burst(self.particles, heart.pos, (255, 120, 150), 10, 80, 0.35, 3)
                self.audio.play("heal")
            else:
                kept.append(heart)
        self.hearts = kept

    def update_fx(self, dt):
        self.particles = [p for p in self.particles if p.update(dt)]
        if len(self.particles) > 360:
            del self.particles[:-360]
        self.floaters = [f for f in self.floaters if f.update(dt)]

    def damage_enemy(self, enemy, hit_pos, damage=1):
        if not enemy.alive:
            return
        enemy.hp -= damage
        enemy.flash = 0.1
        burst(self.particles, hit_pos, enemy.color, 6, 110, 0.28, 3)
        if enemy.hp > 0:
            self.audio.play("hit")
            return
        enemy.alive = False
        enemy.dying = 0.28
        self.add_score(enemy.score)
        self.popup(enemy.pos, f"+{enemy.score}", GOLD)
        burst(self.particles, enemy.pos, enemy.color, 28 if enemy.kind in ("brute", "secret") else 16, 220, 0.5, 5)
        ring(self.particles, enemy.pos, (255, 244, 230), enemy.radius)
        self.shake = min(14, self.shake + (10 if enemy.kind == "secret" else 8 if enemy.kind == "brute" else 3.5))
        if enemy.kind == "brute":
            self.hitstop = 0.045
            self.audio.play("boom")
            self.hearts.append(Heart(pygame.Vector2(enemy.pos)))
        elif enemy.kind == "secret":
            self.hitstop = 0.06
            self.pending_upgrades += 1
            self.popup(enemy.pos + pygame.Vector2(0, -36), "UPGRADE", self.theme["accent"])
            self.audio.play("boom")
        else:
            self.audio.play("pop")

    def move_scale(self):
        if self.theme["hazard"] != "slow":
            return 1.0
        for hazard in self.hazards:
            if self.player.pos.distance_to(hazard["pos"]) < hazard["radius"]:
                return 0.52
        return 1.0

    def touch_hazards(self):
        if self.theme["hazard"] != "burn" or not self.player.alive:
            return
        for hazard in self.hazards:
            if self.player.pos.distance_to(hazard["pos"]) < hazard["radius"] - 6:
                self.hurt_player(hazard["pos"])
                return

    def update_secrets(self):
        if not self.player.alive:
            return
        for spot in self.secrets:
            if spot["woken"] or self.player.pos.distance_to(spot["pos"]) > 170:
                continue
            spot["woken"] = True
            boss = Enemy("secret", spot["pos"])
            boss.color = self.theme["boss_color"]
            boss.name = spot["name"]
            boss.spawn = 0.45
            self.keep_inside(boss.pos, boss.radius)
            self.enemies.append(boss)
            self.popup(boss.pos + pygame.Vector2(0, -48), spot["name"], self.theme["accent"])
            ring(self.particles, boss.pos, boss.color, 20)
            self.shake = min(14, self.shake + 8)
            self.audio.play("boom")

    def hurt_player(self, source):
        if not self.player.alive or self.player.iframe > 0:
            return
        self.player.hearts -= 1
        self.player.iframe = 0.95
        self.shake = min(14, self.shake + 6)
        away = self.player.pos - pygame.Vector2(source)
        if away.length_squared() > 1:
            self.player.vel += away.normalize() * 260
        burst(self.particles, self.player.pos, (255, 90, 100), 12, 160, 0.35, 4)
        if self.player.hearts <= 0:
            self.player.hearts = 0
            self.player.alive = False
            self.death_t = 0.85
            burst(self.particles, self.player.pos, CYAN, 26, 260, 0.55, 5)
            ring(self.particles, self.player.pos, (255, 255, 255), 18)
            self.shake = 12
            self.audio.play("boom")
            self.remember_score()
        else:
            self.audio.play("hurt")

    def remember_score(self):
        if self.score > self.high:
            self.high = self.score
            self.new_best = True
        if not self.new_best:
            return
        try:
            write_high_score(self.high)
        except OSError:
            pass

    def add_score(self, amount):
        self.score += amount
        self.remember_score()
        while self.score >= self.upgrade_at:
            self.pending_upgrades += 1
            self.upgrade_at += UPGRADE_EVERY

    def maybe_open_upgrade(self):
        if self.state != "play" or not self.player.alive or self.banner > 0 or self.pending_upgrades <= 0:
            return
        offers = self.roll_offers()
        if not offers:
            self.pending_upgrades = 0
            return
        self.pending_upgrades -= 1
        self.offers = offers
        self.state = "upgrade"
        self.player.fire_cd = 0.25
        self.audio.play("wave")

    def roll_offers(self):
        pool = [key for key, _name, _blurb, _color in UPGRADES if self.mods[key] < 3]
        random.shuffle(pool)
        return pool[:3]

    def choose_upgrade(self, index):
        if self.state != "upgrade" or index < 0 or index >= len(self.offers):
            return
        key = self.offers[index]
        self.mods[key] = min(3, self.mods[key] + 1)
        self.sync_gun()
        self.audio.play("heal")
        self.player.fire_cd = 0.25
        if self.pending_upgrades > 0:
            offers = self.roll_offers()
            if offers:
                self.pending_upgrades -= 1
                self.offers = offers
                self.audio.play("wave")
                return
        self.offers = []
        self.state = "play"

    def gun_stats(self):
        rapid = self.mods["rapid"]
        heavy = self.mods["heavy"]
        cooldown = FIRE_COOLDOWN * (0.8 ** rapid) * (1 + 0.15 * heavy)
        damage = 1 + heavy
        pierce = self.mods["pierce"]
        speed = PLAYER_BULLET_SPEED * (1 - 0.07 * heavy)
        radius = 4 + heavy * 1.4
        return cooldown, damage, pierce, speed, radius, self.bullet_color()

    def bullet_color(self):
        if self.mods["heavy"] >= self.mods["pierce"] and self.mods["heavy"] > 0:
            return (255, 196, 96)
        if self.mods["pierce"] > 0:
            return (150, 235, 170)
        if self.mods["spread"] > 0:
            return (206, 170, 255)
        if self.mods["rapid"] > 0:
            return (140, 230, 255)
        return (170, 245, 255)

    def sync_gun(self):
        best = max(self.mods, key=self.mods.get)
        if self.mods[best] <= 0:
            self.player.gun_color = (48, 54, 68)
            return
        self.player.gun_color = UPGRADE_BY_KEY[best][3]

    def launch_bullets(self, bullet):
        spread = self.mods["spread"]
        if spread <= 0:
            angles = (0,)
        elif spread == 1:
            angles = (-0.16, 0, 0.16)
        elif spread == 2:
            angles = (-0.24, 0, 0.24)
        else:
            angles = (-0.32, -0.16, 0, 0.16, 0.32)
        for angle in angles:
            c, s = math.cos(angle), math.sin(angle)
            vel = pygame.Vector2(bullet.vel.x * c - bullet.vel.y * s, bullet.vel.x * s + bullet.vel.y * c)
            if angle == 0:
                bullet.vel = vel
                self.bullets.append(bullet)
            else:
                self.bullets.append(Bullet(
                    bullet.pos, vel, True, damage=bullet.damage, pierce=bullet.pierce,
                    radius=bullet.radius, color=bullet.color,
                ))

    def popup(self, pos, text, color):
        self.floaters.append(Floater(pos, self.small.render(text, True, color)))

    def keep_inside(self, pos, radius):
        for _ in range(2):
            pos.x = min(max(pos.x, self.arena.left + radius), self.arena.right - radius)
            pos.y = min(max(pos.y, self.arena.top + radius), self.arena.bottom - radius)
            for crate in self.crates:
                push_circle_out_of_rect(pos, radius, crate)

    def view_origin(self):
        if self.state == "start":
            return (WORLD_W - VIEW_W) / 2, (WORLD_H - VIEW_H) / 2
        x = self.player.pos.x - VIEW_W / 2 - self.offset[0]
        y = self.player.pos.y - VIEW_H / 2 - self.offset[1]
        return (
            max(0, min(WORLD_W - VIEW_W, x)),
            max(0, min(WORLD_H - VIEW_H, y)),
        )

    def view_rect(self):
        x, y = self.view_origin()
        rect = pygame.Rect(round(x), round(y), VIEW_W, VIEW_H)
        rect.x = max(0, min(rect.x, WORLD_W - VIEW_W))
        rect.y = max(0, min(rect.y, WORLD_H - VIEW_H))
        return rect

    def mouse_world(self):
        mx, my = pygame.mouse.get_pos()
        mx = min(max(mx, 0), VIEW_W - 1)
        my = min(max(my, 0), VIEW_H - 1)
        view = self.view_rect()
        return pygame.Vector2(view.x + mx, view.y + my)

    def draw(self):
        if self.state == "start":
            self.draw_title()
        else:
            self.draw_world(self.world)
            self.screen.fill(WALL)
            view = self.view_rect()
            self.screen.blit(self.world, (0, 0), view)
            if self.player.alive and self.player.iframe > 0.72 and self.state == "play":
                self.screen.blit(self.hurt_tint, (0, 0))
            if self.banner > 0 and self.state == "play":
                self.draw_banner()
            self.draw_hud()
            if self.map_open:
                self.draw_panel()
            if self.state == "pause":
                self.draw_pause()
            elif self.state == "over":
                self.draw_over()
            elif self.state == "upgrade":
                self.draw_upgrade()
            self.draw_map_toggle()
        self.draw_crosshair()
        if not self.headless:
            pygame.display.flip()

    def draw_world(self, surf):
        self.draw_arena(surf)
        for heart in self.hearts:
            heart.draw(surf)
        for particle in self.particles:
            if particle.shape != "shell":
                continue
            particle.draw(surf)
        for enemy in self.enemies:
            enemy.draw(surf)
        if self.player.alive:
            flicker = self.player.iframe > 0 and self.player.dash_t <= 0 and int(self.time * 18) % 2 == 0
            if not flicker:
                for ghost in self.player.ghosts:
                    self.player.draw(surf, ghost=ghost, fade=ghost[4] / 0.16 * 0.45)
                self.player.draw(surf)
        for bullet in self.bullets:
            bullet.draw(surf)
        for particle in self.particles:
            if particle.shape == "shell":
                continue
            particle.draw(surf)
        for floater in self.floaters:
            floater.draw(surf)

    def draw_arena(self, surf):
        theme = self.theme
        surf.fill(theme["wall"])
        pygame.draw.rect(surf, theme["floor"], self.arena)
        for x, y, w in self.scuffs:
            pygame.draw.ellipse(surf, theme["scuff"], (x - w, y - w * 0.35, w * 2, w * 0.7))
        step = 40
        x = self.arena.left
        while x <= self.arena.right:
            pygame.draw.line(surf, theme["grid"], (x, self.arena.top), (x, self.arena.bottom))
            x += step
        y = self.arena.top
        while y <= self.arena.bottom:
            pygame.draw.line(surf, theme["grid"], (self.arena.left, y), (self.arena.right, y))
            y += step
        pygame.draw.circle(surf, theme["grid"], (WORLD_W // 2, WORLD_H // 2), 74, 2)
        for hazard in self.hazards:
            pulse = 6 * math.sin(self.time * 3 + hazard["pos"].x * 0.01)
            radius = int(hazard["radius"] + pulse)
            color = theme["hazard_color"]
            if theme["hazard"] == "burn":
                pygame.draw.circle(surf, color, hazard["pos"], max(8, radius))
                pygame.draw.circle(surf, (255, 210, 90), hazard["pos"], max(4, int(radius * 0.38)))
            else:
                pygame.draw.circle(surf, color, hazard["pos"], max(8, radius), 10)
        pygame.draw.rect(surf, theme["wall_edge"], self.arena, 3)
        for crate in self.crates:
            pygame.draw.rect(surf, theme["crate_dark"], crate.inflate(6, 6), border_radius=8)
            pygame.draw.rect(surf, theme["crate"], crate, border_radius=6)
            brace = crate.inflate(-16, -16)
            pygame.draw.line(surf, theme["crate_light"], brace.topleft, brace.bottomright, 3)
            pygame.draw.line(surf, theme["crate_light"], brace.topright, brace.bottomleft, 3)
            pygame.draw.rect(surf, theme["crate_light"], crate, 2, border_radius=6)

    def draw_banner(self):
        t = 1 - self.banner / 1.2
        scale = 1.4 - 0.4 * min(1.0, t * 1.5)
        title = self.big.render(f"WAVE {self.wave}", True, TEXT)
        size = (max(1, int(title.get_width() * scale)), max(1, int(title.get_height() * scale)))
        popped = pygame.transform.smoothscale(title, size)
        popped.set_alpha(int(255 * min(1.0, self.banner / 0.25, max(0.0, t) * 4)))
        self.screen.blit(popped, popped.get_rect(center=(VIEW_W // 2, VIEW_H // 2 - 16)))
        sub = self.font.render("GET READY", True, AMBER)
        sub.set_alpha(popped.get_alpha())
        self.screen.blit(sub, sub.get_rect(center=(VIEW_W // 2, VIEW_H // 2 + 48)))

    def draw_hud(self):
        pulse = 1.15 + math.sin(self.time * 8) * 0.12 if self.player.hearts == 1 else 1.0
        for i in range(MAX_HEARTS):
            scale = pulse if i == 0 and self.player.hearts == 1 else 1.0
            draw_heart(self.screen, 28 + i * 26, 30, i < self.player.hearts, scale)
        score = self.font.render(str(self.score), True, TEXT)
        self.screen.blit(score, score.get_rect(midtop=(VIEW_W // 2, 16)))
        best = self.small.render(f"BEST  {self.high}", True, GOLD)
        self.screen.blit(best, best.get_rect(midtop=(VIEW_W // 2, 48)))
        wave = self.small.render(f"WAVE {self.wave}", True, MUTED)
        self.screen.blit(wave, (22, 48))
        self.draw_dash_meter()
        if self.audio.muted:
            tag = self.small.render("MUTED", True, AMBER)
            self.screen.blit(tag, tag.get_rect(topright=(VIEW_W - 22, 48)))

    def draw_dash_meter(self):
        rect = pygame.Rect(VIEW_W - 118, 24, 96, 10)
        pygame.draw.rect(self.screen, (16, 18, 26), rect, border_radius=4)
        if self.player.dash_t > 0:
            fill = 1.0
        elif self.player.dash_cd <= 0:
            fill = 1.0
        else:
            fill = 1 - self.player.dash_cd / DASH_COOLDOWN
        ready = self.player.dash_cd <= 0 and self.player.dash_t <= 0
        color = self.theme["accent"] if ready else (70, 110, 140)
        inner = rect.inflate(-2, -2)
        inner.width = max(0, int(inner.width * fill))
        if inner.width:
            pygame.draw.rect(self.screen, color, inner, border_radius=3)
        label = self.small.render("DASH", True, TEXT if ready else MUTED)
        self.screen.blit(label, label.get_rect(midbottom=(rect.centerx, rect.top - 2)))

    def draw_title(self):
        self.draw_arena(self.world)
        view = self.view_rect()
        self.screen.fill((12, 14, 20))
        self.screen.blit(self.world, (0, 0), view)
        self.screen.blit(self.shade, (0, 0))
        shift = pygame.Vector2(view.topleft)
        for enemy in self.decor:
            enemy.pos -= shift
            enemy.draw(self.screen)
            enemy.pos += shift
        self.preview.pos -= shift
        self.preview.draw(self.screen)
        self.preview.pos += shift
        if self.map_open:
            self.draw_panel()
        title = "MINI SHOOTER"
        x = VIEW_W / 2 - sum(self.big.render(ch, True, TEXT).get_width() for ch in title) / 2
        for i, ch in enumerate(title):
            glyph = self.big.render(ch, True, TEXT if ch != " " else TEXT)
            y = 36 + math.sin(self.time * 3 + i * 0.45) * 4
            self.screen.blit(glyph, (x, y))
            x += glyph.get_width()
        sub = self.font.render("Pick a map", True, MUTED)
        self.screen.blit(sub, sub.get_rect(midtop=(VIEW_W // 2, 142)))
        self.draw_map_cards()
        hint = self.small.render("A boss sleeps in every corner", True, self.theme["accent"])
        self.screen.blit(hint, hint.get_rect(midtop=(VIEW_W // 2, 292)))
        best = self.small.render(f"BEST  {self.high}", True, GOLD)
        self.screen.blit(best, best.get_rect(midtop=(VIEW_W // 2, 322)))
        if self.button("PLAY", (VIEW_W // 2, 390)):
            self.begin()
        if self.button("EXIT", (VIEW_W // 2, 458), primary=False):
            self.leave()
        help_1 = self.small.render("WASD move     mouse aim     hold click to shoot     Shift dash", True, TEXT)
        help_2 = self.small.render("Every 100 points upgrades your gun     Tab map     M mute     Esc pause", True, MUTED)
        self.screen.blit(help_1, help_1.get_rect(midbottom=(VIEW_W // 2, HEIGHT - 58)))
        self.screen.blit(help_2, help_2.get_rect(midbottom=(VIEW_W // 2, HEIGHT - 32)))
        self.draw_map_toggle()

    def draw_map_cards(self):
        card_w, card_h, gap = 250, 78, 16
        total = len(MAPS) * card_w + (len(MAPS) - 1) * gap
        left = VIEW_W // 2 - total // 2
        for index, theme in enumerate(MAPS):
            rect = pygame.Rect(left + index * (card_w + gap), 186, card_w, card_h)
            selected = index == self.map_index
            hot = rect.collidepoint(pygame.mouse.get_pos())
            fill = theme["panel"] if not hot else tuple(min(255, c + 18) for c in theme["panel"])
            pygame.draw.rect(self.screen, fill, rect, border_radius=12)
            pygame.draw.rect(self.screen, theme["accent"] if selected or hot else (70, 76, 96), rect, 3 if selected else 2, border_radius=12)
            name = self.button_font.render(theme["name"], True, theme["accent"])
            self.screen.blit(name, name.get_rect(midtop=(rect.centerx, rect.top + 14)))
            blurb = self.small.render(theme["blurb"], True, MUTED)
            self.screen.blit(blurb, blurb.get_rect(midtop=(rect.centerx, rect.top + 46)))
            if hot and self.clicked and index != self.map_index:
                self.map_index = index
                self.apply_map()

    def draw_pause(self):
        self.screen.blit(self.shade, (0, 0))
        title = self.big.render("PAUSED", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(VIEW_W // 2, 200)))
        if self.button("RESUME", (VIEW_W // 2, 310)):
            self.state = "play"
            self.player.fire_cd = 0.15
        if self.button("TITLE", (VIEW_W // 2, 378), primary=False):
            self.show_title()

    def draw_over(self):
        self.screen.blit(self.shade, (0, 0))
        title = self.big.render("GAME OVER", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(VIEW_W // 2, 150)))
        score = self.font.render(f"SCORE  {self.score}", True, GOLD)
        self.screen.blit(score, score.get_rect(center=(VIEW_W // 2, 230)))
        note = f"NEW BEST  {self.high}" if self.new_best else f"BEST  {self.high}"
        best = self.small.render(note, True, AMBER if self.new_best else MUTED)
        self.screen.blit(best, best.get_rect(center=(VIEW_W // 2, 272)))
        if self.button("AGAIN", (VIEW_W // 2, 350)):
            self.begin()
        if self.button("TITLE", (VIEW_W // 2, 418), primary=False):
            self.show_title()

    def button(self, text, center, primary=True):
        rect = pygame.Rect(0, 0, 220, 52)
        rect.center = center
        hot = rect.collidepoint(pygame.mouse.get_pos())
        accent = self.theme["accent"]
        if primary:
            fill = tuple(min(255, c + 40) for c in accent) if hot else accent
        else:
            fill = (210, 216, 230) if hot else (54, 62, 80)
        pygame.draw.rect(self.screen, fill, rect, border_radius=12)
        pygame.draw.rect(self.screen, (255, 255, 255), rect, 2, border_radius=12)
        label = self.button_font.render(text, True, INK if primary or hot else TEXT)
        self.screen.blit(label, label.get_rect(center=rect.center))
        return hot and self.clicked

    def map_toggle_rect(self):
        if self.map_open:
            return pygame.Rect(VIEW_W + PANEL_W - 78, 12, 62, 26)
        return pygame.Rect(VIEW_W - 80, 72, 62, 26)

    def toggle_map(self):
        self.map_open = not self.map_open
        write_map_open(self.map_open)
        self.apply_window()

    def apply_window(self):
        width = WIDTH if self.map_open else VIEW_W
        if self.headless:
            self.screen = pygame.Surface((width, HEIGHT))
            return
        self.screen = pygame.display.set_mode((width, HEIGHT))
        pygame.mouse.set_visible(False)

    def draw_map_toggle(self):
        rect = self.map_toggle_rect()
        hot = rect.collidepoint(pygame.mouse.get_pos())
        accent = self.theme["accent"]
        fill = tuple(min(255, c + 36) for c in accent) if hot else (18, 22, 32)
        pygame.draw.rect(self.screen, fill, rect, border_radius=8)
        pygame.draw.rect(self.screen, accent, rect, 2, border_radius=8)
        label = self.small.render("HIDE" if self.map_open else "MAP", True, INK if hot else TEXT)
        self.screen.blit(label, label.get_rect(center=rect.center))

    def draw_panel(self):
        panel = pygame.Rect(VIEW_W, 0, PANEL_W, HEIGHT)
        pygame.draw.rect(self.screen, self.theme["panel"], panel)
        pygame.draw.line(self.screen, self.theme["wall_edge"], (VIEW_W, 0), (VIEW_W, HEIGHT))
        label = self.small.render(self.theme["name"].upper(), True, self.theme["accent"])
        self.screen.blit(label, (VIEW_W + 18, 14))
        frame = pygame.Rect(VIEW_W + 16, 42, PANEL_W - 32, 250)
        pygame.draw.rect(self.screen, (8, 10, 16), frame, border_radius=8)
        pygame.draw.rect(self.screen, self.theme["wall_edge"], frame, 2, border_radius=8)
        fitted = self.fit_map(frame.inflate(-12, -12))
        pygame.draw.rect(self.screen, self.theme["floor"], fitted)
        for hazard in self.hazards:
            pygame.draw.circle(self.screen, self.theme["hazard_color"], self.map_point(fitted, hazard["pos"]), 3)
        for crate in self.crates:
            rect = pygame.Rect(
                fitted.x + crate.x / WORLD_W * fitted.w,
                fitted.y + crate.y / WORLD_H * fitted.h,
                max(2, crate.w / WORLD_W * fitted.w),
                max(2, crate.h / WORLD_H * fitted.h),
            )
            pygame.draw.rect(self.screen, self.theme["crate"], rect)
        if self.state == "start":
            focus, angle, blips = self.preview.pos, self.preview.angle, self.decor
        else:
            focus, angle, blips = self.player.pos, self.player.angle, [e for e in self.enemies if e.alive]
        view = self.view_rect()
        seen = pygame.Rect(
            fitted.x + view.x / WORLD_W * fitted.w,
            fitted.y + view.y / WORLD_H * fitted.h,
            max(2, VIEW_W / WORLD_W * fitted.w),
            max(2, VIEW_H / WORLD_H * fitted.h),
        )
        pygame.draw.rect(self.screen, (120, 150, 180), seen, 1)
        for blip in blips:
            spot = self.map_point(fitted, blip.pos)
            pygame.draw.circle(self.screen, blip.color, spot, 3)
        spot = self.map_point(fitted, focus)
        pygame.draw.circle(self.screen, CYAN, spot, 4)
        nose = (spot[0] + math.cos(angle) * 8, spot[1] + math.sin(angle) * 8)
        pygame.draw.line(self.screen, (255, 255, 255), spot, nose, 2)

        gun = self.small.render("GUN", True, MUTED)
        self.screen.blit(gun, (VIEW_W + 18, frame.bottom + 18))
        if self.state == "start":
            hint = self.small.render("Every 100 points", True, TEXT)
            self.screen.blit(hint, (VIEW_W + 18, frame.bottom + 46))
            hint_2 = self.small.render("you upgrade.", True, TEXT)
            self.screen.blit(hint_2, (VIEW_W + 18, frame.bottom + 68))
            return
        y = frame.bottom + 46
        for key, name, _blurb, color in UPGRADES:
            level = self.mods[key]
            mark = "●" * level + "○" * (3 - level)
            row = self.small.render(f"{name}  {mark}", True, color if level else MUTED)
            self.screen.blit(row, (VIEW_W + 18, y))
            y += 24
        y += 10
        progress = self.small.render("NEXT UPGRADE", True, MUTED)
        self.screen.blit(progress, (VIEW_W + 18, y))
        bar = pygame.Rect(VIEW_W + 18, y + 26, PANEL_W - 36, 10)
        pygame.draw.rect(self.screen, (8, 10, 16), bar, border_radius=4)
        filled = bar.inflate(-2, -2)
        filled.width = max(0, int(filled.width * (self.score % UPGRADE_EVERY) / UPGRADE_EVERY))
        if filled.width:
            pygame.draw.rect(self.screen, GOLD, filled, border_radius=3)
        count = self.small.render(f"{self.score % UPGRADE_EVERY}/{UPGRADE_EVERY}", True, TEXT)
        self.screen.blit(count, count.get_rect(topright=(bar.right, bar.bottom + 4)))

    def fit_map(self, bounds):
        aspect = WORLD_W / WORLD_H
        width = bounds.w
        height = width / aspect
        if height > bounds.h:
            height = bounds.h
            width = height * aspect
        rect = pygame.Rect(0, 0, int(width), int(height))
        rect.center = bounds.center
        return rect

    def map_point(self, fitted, pos):
        return (
            fitted.x + pos.x / WORLD_W * fitted.w,
            fitted.y + pos.y / WORLD_H * fitted.h,
        )

    def draw_upgrade(self):
        self.screen.blit(self.shade, (0, 0))
        title = self.big.render("UPGRADE", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(VIEW_W // 2, 118)))
        sub = self.font.render("Pick a weapon boost", True, GOLD)
        self.screen.blit(sub, sub.get_rect(center=(VIEW_W // 2, 176)))
        card_w, card_h, gap = 230, 168, 22
        total = len(self.offers) * card_w + max(0, len(self.offers) - 1) * gap
        left = VIEW_W // 2 - total // 2
        for index, key in enumerate(self.offers):
            _key, name, blurb, color = UPGRADE_BY_KEY[key]
            rect = pygame.Rect(left + index * (card_w + gap), 250, card_w, card_h)
            hot = rect.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(self.screen, (28, 34, 48) if not hot else (40, 48, 68), rect, border_radius=14)
            pygame.draw.rect(self.screen, color, rect, 3, border_radius=14)
            heading = self.button_font.render(name, True, color)
            self.screen.blit(heading, heading.get_rect(midtop=(rect.centerx, rect.top + 28)))
            level = self.mods[key]
            change = self.small.render(f"LV {level}  →  {level + 1}", True, TEXT)
            self.screen.blit(change, change.get_rect(midtop=(rect.centerx, rect.top + 72)))
            detail = self.small.render(blurb, True, MUTED)
            self.screen.blit(detail, detail.get_rect(midtop=(rect.centerx, rect.top + 108)))
            key_name = self.small.render(str(index + 1), True, INK)
            badge = pygame.Rect(0, 0, 28, 28)
            badge.midbottom = (rect.centerx, rect.bottom - 16)
            pygame.draw.rect(self.screen, color, badge, border_radius=6)
            self.screen.blit(key_name, key_name.get_rect(center=badge.center))
            if hot and self.clicked:
                self.choose_upgrade(index)

    def draw_crosshair(self):
        x, y = pygame.mouse.get_pos()
        if x >= VIEW_W:
            return
        aimed = False
        if self.state == "play":
            world = self.mouse_world()
            aimed = any(
                enemy.alive and world.distance_to(enemy.pos) < enemy.radius + 8
                for enemy in self.enemies
            )
        color = (255, 96, 96) if aimed else CYAN
        pygame.draw.circle(self.screen, color, (x, y), 11, 2)
        pygame.draw.line(self.screen, color, (x - 16, y), (x - 5, y), 2)
        pygame.draw.line(self.screen, color, (x + 5, y), (x + 16, y), 2)
        pygame.draw.line(self.screen, color, (x, y - 16), (x, y - 5), 2)
        pygame.draw.line(self.screen, color, (x, y + 5), (x, y + 16), 2)
        pygame.draw.circle(self.screen, color, (x, y), 2)


async def main():
    await Game().run()
