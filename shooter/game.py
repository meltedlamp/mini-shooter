"""Arena loop: waves, collisions, menus and the main draw."""

import math
import random

import pygame

from .actors import (
    Enemy, Heart, Player, circle_hits_rect, draw_heart, push_circle_out_of_rect,
)
from .audio import Audio
from .fx import Floater, Particle, burst, ring
from .scores import read_high_score, write_high_score
from .settings import (
    AMBER, CRATE, CRATE_DARK, CRATE_LIGHT, CRATES, CYAN, DASH_COOLDOWN, FLOOR, FPS, GOLD, GRID,
    HEIGHT, INK, MARGIN, MAX_HEARTS, MUTED, TEXT, TITLE, WALL, WALL_EDGE, WIDTH,
)


class Game:
    def __init__(self, *, headless=False):
        self.headless = headless
        try:
            pygame.mixer.pre_init(44100, -16, 1, 512)
        except pygame.error:
            pass
        pygame.init()
        pygame.display.set_caption(TITLE)
        if headless:
            self.screen = pygame.Surface((WIDTH, HEIGHT))
        else:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
            pygame.mouse.set_visible(False)
        self.world = pygame.Surface((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("segoeui", 28)
        self.small = pygame.font.SysFont("segoeui", 18)
        self.big = pygame.font.SysFont("segoeui", 64, bold=True)
        self.button_font = pygame.font.SysFont("segoeui", 26, bold=True)
        self.audio = Audio()
        self.arena = pygame.Rect(MARGIN, MARGIN, WIDTH - MARGIN * 2, HEIGHT - MARGIN * 2)
        self.crates = [pygame.Rect(rect) for rect in CRATES]
        rng = random.Random(4)
        self.scuffs = [
            (rng.randint(self.arena.left + 20, self.arena.right - 20),
             rng.randint(self.arena.top + 20, self.arena.bottom - 20),
             rng.randint(16, 40))
            for _ in range(16)
        ]
        self.shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.shade.fill((6, 8, 14, 188))
        self.hurt_tint = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.hurt_tint.fill((255, 36, 48, 55))
        self.high = read_high_score()
        self.running = True
        self.clicked = False
        self.time = 0.0
        self.offset = (0, 0)
        self.state = "start"
        self.decor = [
            Enemy("brute", (128, 188)),
            Enemy("grunt", (828, 168)),
            Enemy("shooter", (812, 456)),
        ]
        for enemy in self.decor:
            enemy.spawn = 0
        self.preview = Player((168, 468))
        self.reset_run()

    def reset_run(self):
        self.player = Player((WIDTH / 2, HEIGHT / 2))
        self.enemies = []
        self.bullets = []
        self.hearts = []
        self.particles = []
        self.floaters = []
        self.queue = []
        self.wave = 1
        self.banner = 1.2
        self.score = 0
        self.score_saved = False
        self.new_best = False
        self.shake = 0.0
        self.hitstop = 0.0
        self.death_t = 0.0
        self.dust_cd = 0.0

    def run(self):
        while self.running:
            dt = min(0.05, self.clock.tick(FPS) / 1000)
            self.clicked = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    self.on_key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.clicked = True
            self.time += dt
            self.offset = self.compute_offset()
            self.update(dt)
            self.draw()
        pygame.quit()

    def on_key(self, key):
        if key == pygame.K_m:
            self.audio.toggle()
            return
        if key == pygame.K_ESCAPE:
            if self.state == "start":
                self.running = False
            elif self.state == "play":
                self.state = "pause"
            elif self.state == "pause":
                self.state = "play"
                self.player.fire_cd = 0.15
            elif self.state == "over":
                self.state = "start"
        elif key in (pygame.K_RETURN, pygame.K_SPACE) and self.state in ("start", "over"):
            self.begin()

    def begin(self):
        self.reset_run()
        self.state = "play"

    def compute_offset(self):
        if self.state not in ("play", "pause") or self.shake < 0.3:
            return (0, 0)
        angle = random.random() * math.tau
        return (math.cos(angle) * self.shake, math.sin(angle) * self.shake)

    def update(self, dt):
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
        want_fire = pygame.mouse.get_pressed()[0]
        want_dash = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        if self.player.alive:
            was_dashing = self.player.dash_t > 0
            bullet, casing = self.player.update(dt, move, mouse - self.player.pos, want_fire, want_dash)
            self.keep_inside(self.player.pos, self.player.radius)
            if bullet is not None:
                self.bullets.append(bullet)
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
            self.score += bonus
            self.popup(self.player.pos + pygame.Vector2(0, -28), f"+{bonus}", GOLD)
            self.wave += 1
            self.banner = 1.15

    def wave_kinds(self, wave):
        total = min(12, 2 + wave)
        brutes = 2 if wave >= 9 and wave % 3 == 0 else (1 if wave >= 3 and wave % 3 == 0 else 0)
        shooters = 0 if wave == 1 else min(5, wave // 2)
        grunts = max(1, total - brutes - shooters)
        return ["brute"] * brutes + ["shooter"] * shooters + ["grunt"] * grunts

    def spawn_enemy(self, kind, pos=None):
        enemy = Enemy(kind, pos or self.spawn_point())
        self.enemies.append(enemy)
        ring(self.particles, enemy.pos, enemy.color, 8)
        return enemy

    def spawn_point(self):
        for _ in range(24):
            side = random.randrange(4)
            if side == 0:
                pos = pygame.Vector2(random.uniform(self.arena.left + 30, self.arena.right - 30), self.arena.top + 28)
            elif side == 1:
                pos = pygame.Vector2(random.uniform(self.arena.left + 30, self.arena.right - 30), self.arena.bottom - 28)
            elif side == 2:
                pos = pygame.Vector2(self.arena.left + 28, random.uniform(self.arena.top + 30, self.arena.bottom - 30))
            else:
                pos = pygame.Vector2(self.arena.right - 28, random.uniform(self.arena.top + 30, self.arena.bottom - 30))
            if pos.distance_to(self.player.pos) < 190:
                continue
            if any(circle_hits_rect(pos, 24, crate) for crate in self.crates):
                continue
            return pos
        return pygame.Vector2(self.arena.left + 40, self.arena.top + 40)

    def update_enemies(self, dt):
        alive = []
        for enemy in self.enemies:
            shot = enemy.update(dt, self.player, self.crates)
            if shot is not None:
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
                        if enemy.alive and point.distance_to(enemy.pos) < enemy.radius + bullet.radius:
                            self.damage_enemy(enemy, point)
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
                    self.score += 50
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

    def damage_enemy(self, enemy, hit_pos):
        if not enemy.alive:
            return
        enemy.hp -= 1
        enemy.flash = 0.1
        burst(self.particles, hit_pos, enemy.color, 6, 110, 0.28, 3)
        if enemy.hp > 0:
            self.audio.play("hit")
            return
        enemy.alive = False
        enemy.dying = 0.28
        self.score += enemy.score
        self.popup(enemy.pos, f"+{enemy.score}", GOLD)
        burst(self.particles, enemy.pos, enemy.color, 16 if enemy.kind != "brute" else 28, 220, 0.5, 5)
        ring(self.particles, enemy.pos, (255, 244, 230), enemy.radius)
        self.shake = min(14, self.shake + (8 if enemy.kind == "brute" else 3.5))
        if enemy.kind == "brute":
            self.hitstop = 0.045
            self.audio.play("boom")
            self.hearts.append(Heart(pygame.Vector2(enemy.pos)))
        else:
            self.audio.play("pop")

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
            self.commit_score()
        else:
            self.audio.play("hurt")

    def commit_score(self):
        if self.score_saved:
            return
        self.score_saved = True
        if self.score > self.high:
            self.high = self.score
            write_high_score(self.high)
            self.new_best = True

    def popup(self, pos, text, color):
        self.floaters.append(Floater(pos, self.small.render(text, True, color)))

    def keep_inside(self, pos, radius):
        for _ in range(2):
            pos.x = min(max(pos.x, self.arena.left + radius), self.arena.right - radius)
            pos.y = min(max(pos.y, self.arena.top + radius), self.arena.bottom - radius)
            for crate in self.crates:
                push_circle_out_of_rect(pos, radius, crate)

    def mouse_world(self):
        mouse = pygame.Vector2(pygame.mouse.get_pos())
        return mouse - pygame.Vector2(self.offset)

    def draw(self):
        if self.state == "start":
            self.draw_title()
        else:
            self.draw_world(self.world)
            self.screen.fill(WALL)
            self.screen.blit(self.world, self.offset)
            self.draw_hud()
            if self.state == "pause":
                self.draw_pause()
            elif self.state == "over":
                self.draw_over()
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
        if self.player.alive and self.player.iframe > 0.72:
            surf.blit(self.hurt_tint, (0, 0))
        if self.banner > 0 and self.state == "play":
            self.draw_banner(surf)

    def draw_arena(self, surf):
        surf.fill(WALL)
        pygame.draw.rect(surf, FLOOR, self.arena)
        for x, y, w in self.scuffs:
            pygame.draw.ellipse(surf, (26, 30, 42), (x - w, y - w * 0.35, w * 2, w * 0.7))
        step = 40
        x = self.arena.left
        while x <= self.arena.right:
            pygame.draw.line(surf, GRID, (x, self.arena.top), (x, self.arena.bottom))
            x += step
        y = self.arena.top
        while y <= self.arena.bottom:
            pygame.draw.line(surf, GRID, (self.arena.left, y), (self.arena.right, y))
            y += step
        pygame.draw.circle(surf, GRID, (WIDTH // 2, HEIGHT // 2), 74, 2)
        pygame.draw.rect(surf, WALL_EDGE, self.arena, 3)
        for crate in self.crates:
            pygame.draw.rect(surf, CRATE_DARK, crate.inflate(6, 6), border_radius=8)
            pygame.draw.rect(surf, CRATE, crate, border_radius=6)
            brace = crate.inflate(-16, -16)
            pygame.draw.line(surf, CRATE_LIGHT, brace.topleft, brace.bottomright, 3)
            pygame.draw.line(surf, CRATE_LIGHT, brace.topright, brace.bottomleft, 3)
            pygame.draw.rect(surf, CRATE_LIGHT, crate, 2, border_radius=6)

    def draw_banner(self, surf):
        t = 1 - self.banner / 1.2
        scale = 1.4 - 0.4 * min(1.0, t * 1.5)
        title = self.big.render(f"WAVE {self.wave}", True, TEXT)
        size = (max(1, int(title.get_width() * scale)), max(1, int(title.get_height() * scale)))
        popped = pygame.transform.smoothscale(title, size)
        popped.set_alpha(int(255 * min(1.0, self.banner / 0.25, max(0.0, t) * 4)))
        surf.blit(popped, popped.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 16)))
        sub = self.font.render("GET READY", True, AMBER)
        sub.set_alpha(popped.get_alpha())
        surf.blit(sub, sub.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 48)))

    def draw_hud(self):
        pulse = 1.15 + math.sin(self.time * 8) * 0.12 if self.player.hearts == 1 else 1.0
        for i in range(MAX_HEARTS):
            scale = pulse if i == 0 and self.player.hearts == 1 else 1.0
            draw_heart(self.screen, 28 + i * 26, 30, i < self.player.hearts, scale)
        score = self.font.render(str(self.score), True, TEXT)
        self.screen.blit(score, score.get_rect(midtop=(WIDTH // 2, 16)))
        wave = self.small.render(f"WAVE {self.wave}", True, MUTED)
        self.screen.blit(wave, (22, 48))
        self.draw_dash_meter()
        if self.audio.muted:
            tag = self.small.render("MUTED", True, AMBER)
            self.screen.blit(tag, tag.get_rect(topright=(WIDTH - 22, 48)))

    def draw_dash_meter(self):
        rect = pygame.Rect(WIDTH - 118, 24, 96, 10)
        pygame.draw.rect(self.screen, (16, 18, 26), rect, border_radius=4)
        if self.player.dash_t > 0:
            fill = 1.0
        elif self.player.dash_cd <= 0:
            fill = 1.0
        else:
            fill = 1 - self.player.dash_cd / DASH_COOLDOWN
        ready = self.player.dash_cd <= 0 and self.player.dash_t <= 0
        color = CYAN if ready else (70, 110, 140)
        inner = rect.inflate(-2, -2)
        inner.width = max(0, int(inner.width * fill))
        if inner.width:
            pygame.draw.rect(self.screen, color, inner, border_radius=3)
        label = self.small.render("DASH", True, TEXT if ready else MUTED)
        self.screen.blit(label, label.get_rect(midbottom=(rect.centerx, rect.top - 2)))

    def draw_title(self):
        self.draw_arena(self.screen)
        self.screen.blit(self.shade, (0, 0))
        for enemy in self.decor:
            enemy.draw(self.screen)
        self.preview.draw(self.screen)
        title = "MINI SHOOTER"
        x = WIDTH / 2 - sum(self.big.render(ch, True, TEXT).get_width() for ch in title) / 2
        for i, ch in enumerate(title):
            glyph = self.big.render(ch, True, TEXT if ch != " " else TEXT)
            y = 78 + math.sin(self.time * 3 + i * 0.45) * 5
            self.screen.blit(glyph, (x, y))
            x += glyph.get_width()
        sub = self.font.render("A tiny arena blaster", True, MUTED)
        self.screen.blit(sub, sub.get_rect(midtop=(WIDTH // 2, 168)))
        best = self.small.render(f"BEST  {self.high}", True, GOLD)
        self.screen.blit(best, best.get_rect(midtop=(WIDTH // 2, 214)))
        if self.button("PLAY", (WIDTH // 2, 300)):
            self.begin()
        if self.button("EXIT", (WIDTH // 2, 368), primary=False):
            self.running = False
        help_1 = self.small.render("WASD move     mouse aim     hold click to shoot     Shift dash", True, TEXT)
        help_2 = self.small.render("M mute     Esc pause", True, MUTED)
        self.screen.blit(help_1, help_1.get_rect(midbottom=(WIDTH // 2, HEIGHT - 58)))
        self.screen.blit(help_2, help_2.get_rect(midbottom=(WIDTH // 2, HEIGHT - 32)))

    def draw_pause(self):
        self.screen.blit(self.shade, (0, 0))
        title = self.big.render("PAUSED", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 200)))
        if self.button("RESUME", (WIDTH // 2, 310)):
            self.state = "play"
            self.player.fire_cd = 0.15
        if self.button("TITLE", (WIDTH // 2, 378), primary=False):
            self.state = "start"

    def draw_over(self):
        self.screen.blit(self.shade, (0, 0))
        title = self.big.render("GAME OVER", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 150)))
        score = self.font.render(f"SCORE  {self.score}", True, GOLD)
        self.screen.blit(score, score.get_rect(center=(WIDTH // 2, 230)))
        note = "NEW BEST" if self.new_best else f"BEST  {self.high}"
        best = self.small.render(note, True, AMBER if self.new_best else MUTED)
        self.screen.blit(best, best.get_rect(center=(WIDTH // 2, 272)))
        if self.button("AGAIN", (WIDTH // 2, 350)):
            self.begin()
        if self.button("TITLE", (WIDTH // 2, 418), primary=False):
            self.state = "start"

    def button(self, text, center, primary=True):
        rect = pygame.Rect(0, 0, 220, 52)
        rect.center = center
        hot = rect.collidepoint(pygame.mouse.get_pos())
        if primary:
            fill = (255, 206, 96) if hot else (88, 210, 255)
        else:
            fill = (210, 216, 230) if hot else (54, 62, 80)
        pygame.draw.rect(self.screen, fill, rect, border_radius=12)
        pygame.draw.rect(self.screen, (255, 255, 255), rect, 2, border_radius=12)
        label = self.button_font.render(text, True, INK if primary or hot else TEXT)
        self.screen.blit(label, label.get_rect(center=rect.center))
        return hot and self.clicked

    def draw_crosshair(self):
        x, y = pygame.mouse.get_pos()
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


def main():
    Game().run()
