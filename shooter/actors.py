"""Player, enemies, bullets and pickups, drawn with code so they can animate."""

import math
import random

import pygame

from .settings import (
    DASH_COOLDOWN, DASH_SPEED, DASH_TIME, ENEMY_BULLET_SPEED, FIRE_COOLDOWN,
    MAX_HEARTS, PLAYER_BULLET_SPEED, PLAYER_RADIUS, PLAYER_SPEED,
)


def turn_toward(angle, target, dt, speed):
    delta = (target - angle + math.pi) % math.tau - math.pi
    step = speed * dt
    if abs(delta) <= step:
        return target
    return angle + math.copysign(step, delta)


def world_point(origin, angle, x, y):
    c, s = math.cos(angle), math.sin(angle)
    return (origin[0] + x * c - y * s, origin[1] + x * s + y * c)


def world_points(origin, angle, points):
    return [world_point(origin, angle, x, y) for x, y in points]


def push_circle_out_of_rect(pos, radius, rect):
    nearest_x = min(max(pos.x, rect.left), rect.right)
    nearest_y = min(max(pos.y, rect.top), rect.bottom)
    delta = pygame.Vector2(pos.x - nearest_x, pos.y - nearest_y)
    dist_sq = delta.length_squared()
    if dist_sq >= radius * radius:
        return
    if dist_sq < 1e-6:
        gaps = (
            (pos.x - rect.left, -1, 0),
            (rect.right - pos.x, 1, 0),
            (pos.y - rect.top, 0, -1),
            (rect.bottom - pos.y, 0, 1),
        )
        gap, dx, dy = min(gaps, key=lambda item: item[0])
        pos.x += dx * (gap + radius)
        pos.y += dy * (gap + radius)
        return
    dist = math.sqrt(dist_sq)
    pos += delta / dist * (radius - dist)


def circle_hits_rect(pos, radius, rect):
    nearest_x = min(max(pos.x, rect.left), rect.right)
    nearest_y = min(max(pos.y, rect.top), rect.bottom)
    dx = pos.x - nearest_x
    dy = pos.y - nearest_y
    return dx * dx + dy * dy < radius * radius


def sees(a, b, crates):
    start = (a.x, a.y)
    end = (b.x, b.y)
    return not any(crate.clipline(start, end) for crate in crates)


_SHADOW = None


def blit_shadow(surf, pos, scale=1.0):
    global _SHADOW
    if _SHADOW is None:
        _SHADOW = pygame.Surface((52, 22), pygame.SRCALPHA)
        pygame.draw.ellipse(_SHADOW, (0, 0, 0, 80), (0, 0, 52, 22))
    shadow = _SHADOW
    if scale != 1:
        size = (max(1, int(52 * scale)), max(1, int(22 * scale)))
        shadow = pygame.transform.scale(_SHADOW, size)
    surf.blit(shadow, shadow.get_rect(center=(int(pos.x), int(pos.y + 10 * scale))))


def draw_heart(surf, x, y, filled, scale=1.0):
    r = 6.2 * scale
    color = (255, 86, 112) if filled else (72, 78, 96)
    left = (x - r * 0.48, y - r * 0.2)
    right = (x + r * 0.48, y - r * 0.2)
    pygame.draw.circle(surf, color, left, r * 0.58)
    pygame.draw.circle(surf, color, right, r * 0.58)
    pygame.draw.polygon(surf, color, [
        (x - r * 1.02, y + r * 0.05),
        (x + r * 1.02, y + r * 0.05),
        (x, y + r * 1.35),
    ])
    if not filled:
        pygame.draw.circle(surf, (20, 24, 34), left, r * 0.34)
        pygame.draw.circle(surf, (20, 24, 34), right, r * 0.34)


class Bullet:
    def __init__(self, pos, vel, friendly, damage=1, pierce=0, radius=None, color=None):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.friendly = friendly
        self.damage = damage
        self.pierce = pierce
        self.hit_ids = set()
        self.radius = 5 if radius is None and not friendly else (4 if radius is None else radius)
        self.life = 1.15
        self.trail = []
        if color is not None:
            self.color = color
        elif friendly:
            self.color = (170, 245, 255)
        else:
            self.color = (255, 120, 90)
        self.hot = (255, 255, 255) if friendly else (255, 220, 170)

    def advance(self, dt, steps):
        self.life -= dt
        chunk = dt / steps
        hit_points = []
        for _ in range(steps):
            self.pos += self.vel * chunk
            self.trail.append((self.pos.x, self.pos.y))
            hit_points.append(pygame.Vector2(self.pos))
        if len(self.trail) > 7:
            del self.trail[:-7]
        return hit_points

    def draw(self, surf):
        for i, point in enumerate(self.trail):
            fade = (i + 1) / max(1, len(self.trail))
            pygame.draw.circle(surf, self.color, point, max(1, int(2 * fade)))
        if self.vel.length_squared() > 1:
            direction = self.vel.normalize()
            tail = self.pos - direction * (14 if self.friendly else 11)
            pygame.draw.line(surf, self.color, tail, self.pos, max(3, int(self.radius * 0.7)))
        pygame.draw.circle(surf, self.hot, self.pos, max(1, int(round(self.radius))))


class Heart:
    def __init__(self, pos):
        self.pos = pygame.Vector2(pos)
        self.phase = random.random() * math.tau
        self.radius = 14

    def update(self, dt):
        self.phase += dt * 4

    def draw(self, surf):
        bob = math.sin(self.phase) * 4
        glow = 16 + math.sin(self.phase * 2) * 2
        pygame.draw.circle(surf, (90, 24, 40), (self.pos.x, self.pos.y + bob), glow, 2)
        draw_heart(surf, self.pos.x, self.pos.y + bob, True, scale=1.35)


class Player:
    def __init__(self, pos):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2()
        self.angle = 0.0
        self.walk = 0.0
        self.lived = 0.0
        self.recoil = 0.0
        self.flash = 0.0
        self.fire_cd = 0.2
        self.dash_cd = 0.0
        self.dash_t = 0.0
        self.dash_dir = pygame.Vector2(1, 0)
        self.ghost_cd = 0.0
        self.ghosts = []
        self.hearts = MAX_HEARTS
        self.iframe = 0.0
        self.alive = True
        self.radius = PLAYER_RADIUS
        self.gun_color = (48, 54, 68)

    def face(self, aim, dt):
        if aim.length_squared() < 4:
            return pygame.Vector2(math.cos(self.angle), math.sin(self.angle))
        direction = aim.normalize()
        self.angle = turn_toward(self.angle, math.atan2(direction.y, direction.x), dt, 16)
        return pygame.Vector2(math.cos(self.angle), math.sin(self.angle))

    def update(self, dt, move, aim, want_fire, want_dash, fire_cooldown=FIRE_COOLDOWN,
               bullet_speed=PLAYER_BULLET_SPEED, bullet_damage=1, bullet_pierce=0,
               bullet_radius=4, bullet_color=(170, 245, 255), move_scale=1.0):
        """Move, dash and maybe shoot. Returns (bullet, casing_velocity) or (None, None)."""
        self.lived += dt
        self.fire_cd = max(0.0, self.fire_cd - dt)
        self.dash_cd = max(0.0, self.dash_cd - dt)
        self.recoil = max(0.0, self.recoil - dt * 7)
        self.flash = max(0.0, self.flash - dt * 10)
        self.iframe = max(0.0, self.iframe - dt)
        facing = self.face(aim, dt)

        if self.dash_t > 0:
            self.dash_t = max(0.0, self.dash_t - dt)
            self.vel = pygame.Vector2(self.dash_dir) * DASH_SPEED
            self.ghost_cd -= dt
            if self.ghost_cd <= 0:
                self.ghosts.append([self.pos.x, self.pos.y, self.angle, self.walk, 0.16])
                self.ghost_cd = 0.028
        else:
            if move.length_squared() > 0:
                move = move.normalize()
            desired = move * PLAYER_SPEED * move_scale
            self.vel += (desired - self.vel) * min(1.0, 12 * dt)
            if want_dash and self.dash_cd <= 0 and (move.length_squared() > 0 or facing.length_squared() > 0):
                self.dash_dir = move if move.length_squared() > 0 else facing
                self.dash_t = DASH_TIME
                self.dash_cd = DASH_COOLDOWN
                self.iframe = max(self.iframe, DASH_TIME + 0.04)
                self.vel = self.dash_dir * DASH_SPEED

        self.pos += self.vel * dt
        moving = self.vel.length()
        if moving > 30:
            self.walk += moving * dt * 0.045

        for ghost in self.ghosts:
            ghost[4] -= dt
        self.ghosts = [ghost for ghost in self.ghosts if ghost[4] > 0]

        if not want_fire or self.fire_cd > 0 or self.dash_t > 0:
            return None, None
        self.fire_cd = fire_cooldown
        self.recoil = 1.0
        self.flash = 1.0
        self.vel -= facing * 28
        origin = self.pos + facing * 28
        side = pygame.Vector2(-facing.y, facing.x)
        bullet = Bullet(
            origin, facing * bullet_speed, True,
            damage=bullet_damage, pierce=bullet_pierce, radius=bullet_radius, color=bullet_color,
        )
        return bullet, (origin + side * 6, side * 120 - facing * 30)

    def draw(self, surf, ghost=None, fade=1.0):
        if ghost is None:
            pos = self.pos
            angle = self.angle
            walk = self.walk
            recoil = self.recoil
            flash = self.flash
        else:
            pos = pygame.Vector2(ghost[0], ghost[1])
            angle = ghost[2]
            walk = ghost[3]
            recoil = 0
            flash = 0
        if fade < 0.05:
            return
        origin = (pos.x, pos.y + math.sin(self.lived * 3) * fade)
        scale = fade
        blit_shadow(surf, pos, 0.85 * scale)
        swing = math.sin(walk * 2) * 3.5
        boot = tuple(int(c * fade) for c in (64, 70, 88))
        for x, y in ((-5 + swing, -5), (-5 - swing, 5)):
            pygame.draw.circle(surf, boot, world_point(origin, angle, x, y), 4 * scale)
        body = tuple(int(c * fade) for c in (236, 240, 248))
        pygame.draw.circle(surf, tuple(int(c * fade) for c in (170, 178, 196)), origin, 13 * scale)
        pygame.draw.circle(surf, body, origin, 11 * scale)
        visor = world_point(origin, angle, 5, 0)
        pygame.draw.circle(surf, tuple(int(c * fade) for c in (24, 30, 42)), visor, 4.2 * scale)
        pygame.draw.circle(surf, tuple(int(c * fade) for c in (110, 226, 255)), visor, 2.1 * scale)
        kick = recoil * 6
        gun = world_points(origin, angle, (
            (8, -3.2), (24 - kick, -2.2), (24 - kick, 2.2), (8, 3.2),
        ))
        gun_rgb = self.gun_color if ghost is None else (48, 54, 68)
        pygame.draw.polygon(surf, tuple(int(c * fade) for c in gun_rgb), gun)
        grip = world_points(origin, angle, ((6, 1), (11, 1), (11, 6), (6, 6)))
        pygame.draw.polygon(surf, tuple(int(c * fade) for c in (36, 40, 52)), grip)
        if flash > 0.05 and ghost is None:
            tip = world_point(origin, angle, 26 - kick, 0)
            spike = world_point(origin, angle, 26 - kick + 11 * flash, 0)
            pygame.draw.circle(surf, (255, 244, 210), tip, 3 + 4 * flash)
            pygame.draw.circle(surf, (255, 176, 64), tip, 1.6 + 2 * flash)
            pygame.draw.line(surf, (255, 250, 230), tip, spike, 2)


STATS = {
    "grunt": {"hp": 2, "speed": 108, "radius": 16, "score": 10, "color": (255, 148, 70)},
    "shooter": {"hp": 3, "speed": 80, "radius": 15, "score": 25, "color": (186, 126, 255)},
    "brute": {"hp": 8, "speed": 64, "radius": 26, "score": 60, "color": (255, 82, 104)},
    "secret": {"hp": 20, "speed": 72, "radius": 32, "score": 180, "color": (140, 186, 220)},
}


class Enemy:
    def __init__(self, kind, pos):
        stats = STATS[kind]
        self.kind = kind
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2()
        self.hp = stats["hp"]
        self.max_hp = stats["hp"]
        self.speed = stats["speed"]
        self.radius = stats["radius"]
        self.score = stats["score"]
        self.color = stats["color"]
        self.angle = random.random() * math.tau
        self.walk = random.random() * 6
        self.lived = random.random() * 4
        self.flash = 0.0
        self.spawn = 0.32
        self.dying = 0.0
        self.alive = True
        self.shot_cd = random.uniform(0.35, 1.15)
        self.strafe = random.choice((-1.0, 1.0))
        self.strafe_t = random.uniform(0.7, 1.5)
        self.mode = "chase"
        self.mode_t = 0.0
        self.charge_dir = pygame.Vector2(1, 0)
        self.secret_cd = random.uniform(0.6, 1.2)
        self.name = ""

    def _toward_player(self, player):
        delta = player.pos - self.pos
        dist = delta.length()
        if dist < 0.001:
            return pygame.Vector2(1, 0), 0.0
        return delta / dist, dist

    def update(self, dt, player, crates):
        self.lived += dt
        self.flash = max(0.0, self.flash - dt)
        if self.spawn > 0:
            self.spawn = max(0.0, self.spawn - dt)
        if not self.alive:
            self.dying -= dt
            return None
        self.walk += max(40.0, self.vel.length()) * dt * 0.04
        direction, dist = self._toward_player(player)
        self.strafe_t -= dt
        if self.strafe_t <= 0:
            self.strafe *= -1
            self.strafe_t = random.uniform(0.8, 1.6)
        side = pygame.Vector2(-direction.y, direction.x) * self.strafe
        shot = None

        if self.kind == "secret":
            desired, shot = self._secret(dt, direction, dist)
        elif self.kind == "brute":
            desired, shot = self._brute(dt, direction, dist)
        elif self.kind == "shooter":
            desired, shot = self._shooter(dt, player, crates, direction, dist, side)
        else:
            desired = direction * self.speed

        if self.mode == "charge":
            self.vel = desired
        else:
            self.vel += (desired - self.vel) * min(1.0, 7 * dt)
        self.pos += self.vel * dt
        face = self.charge_dir if self.mode == "charge" else direction
        self.angle = turn_toward(self.angle, math.atan2(face.y, face.x), dt, 8)
        return shot

    def _brute(self, dt, direction, dist):
        if self.mode == "windup":
            self.mode_t -= dt
            self.charge_dir = pygame.Vector2(direction)
            if self.mode_t <= 0:
                self.mode = "charge"
                self.mode_t = 0.36
            return pygame.Vector2(), None
        if self.mode == "charge":
            self.mode_t -= dt
            if self.mode_t <= 0:
                self.mode = "chase"
                self.shot_cd = 1.25
            return self.charge_dir * 430, None
        self.shot_cd -= dt
        if self.spawn <= 0 and dist < 240 and self.shot_cd <= 0:
            self.mode = "windup"
            self.mode_t = 0.5
            self.charge_dir = pygame.Vector2(direction)
            return pygame.Vector2(), None
        return direction * self.speed, None

    def _shooter(self, dt, player, crates, direction, dist, side):
        self.shot_cd -= dt
        visible = sees(self.pos, player.pos, crates)
        if not visible:
            move = side
        elif dist > 270:
            move = direction
        elif dist < 150:
            move = -direction
        else:
            move = side
        shot = None
        if self.spawn <= 0 and visible and dist < 540 and self.shot_cd <= 0:
            self.shot_cd = random.uniform(1.05, 1.5)
            spread = random.uniform(-0.16, 0.16)
            angle = math.atan2(direction.y, direction.x) + spread
            facing = pygame.Vector2(math.cos(angle), math.sin(angle))
            origin = self.pos + facing * (self.radius + 8)
            shot = Bullet(origin, facing * ENEMY_BULLET_SPEED, False)
        return move * self.speed, shot

    def _secret(self, dt, direction, dist):
        desired, _shot = self._brute(dt, direction, dist)
        shots = []
        if self.mode == "chase" and self.spawn <= 0 and dist < 700:
            self.secret_cd -= dt
            if self.secret_cd <= 0:
                self.secret_cd = 1.7
                base = math.atan2(direction.y, direction.x)
                for spread in (-0.4, 0.0, 0.4):
                    angle = base + spread
                    facing = pygame.Vector2(math.cos(angle), math.sin(angle))
                    origin = self.pos + facing * (self.radius + 10)
                    shots.append(Bullet(origin, facing * (ENEMY_BULLET_SPEED * 0.85), False, color=self.color))
        return desired, shots or None

    def draw(self, surf):
        scale = 1.0
        if self.spawn > 0 and self.alive:
            scale = 0.25 + 0.75 * (1 - self.spawn / 0.32)
        if not self.alive:
            scale = max(0.05, self.dying / 0.28)
        origin = (self.pos.x, self.pos.y + math.sin(self.lived * 3 + self.walk) * 1.2)
        blit_shadow(surf, self.pos, scale * (self.radius / 16))
        squash = math.sin(self.walk * 2) * (0.1 if self.mode == "charge" else 0.06)
        wide = self.radius * scale * (1.08 + squash)
        tall = self.radius * scale * (1.08 - squash)
        color = (255, 255, 255) if self.flash > 0.04 else self.color
        body = pygame.Rect(0, 0, wide * 2, tall * 2)
        body.center = origin
        dark = tuple(max(0, c - 50) for c in self.color)
        pygame.draw.ellipse(surf, dark, body.inflate(6 * scale, 6 * scale))
        pygame.draw.ellipse(surf, color, body)
        if self.kind == "secret" and self.alive and scale > 0.5:
            pygame.draw.circle(surf, color, origin, int(self.radius * scale + 12), 3)
            pygame.draw.circle(surf, dark, origin, max(4, int(self.radius * scale * 0.42)))
        if self.kind == "brute" and self.alive and scale > 0.55:
            pygame.draw.ellipse(surf, dark, body.inflate(-10 * scale, -8 * scale), max(1, int(3 * scale)))
        if self.kind == "shooter":
            gun = world_points(origin, self.angle, (
                (self.radius * 0.2, -3), (self.radius + 10, -2), (self.radius + 10, 2), (self.radius * 0.2, 3),
            ))
            pygame.draw.polygon(surf, (48, 28, 72), gun)
        eye = (255, 248, 240)
        pupil = (24, 16, 28)
        look = 2.4 * scale
        for y in (-4.2 * scale, 4.2 * scale):
            center = world_point(origin, self.angle, self.radius * 0.25, y)
            pygame.draw.circle(surf, eye, center, 3.1 * scale)
            pygame.draw.circle(surf, pupil, world_point(center, self.angle, look, 0), 1.5 * scale)
        if self.mode == "windup":
            pulse = 0.5 + 0.5 * math.sin(self.lived * 28)
            pygame.draw.circle(surf, (255, 90, 100), origin, int(self.radius + 8 + pulse * 8), 2)
            end = self.pos + self.charge_dir * (78 + pulse * 16)
            pygame.draw.line(surf, (255, 140, 150), self.pos, end, 3)
            pygame.draw.circle(surf, (255, 220, 220), end, 4)
        if self.mode == "charge":
            back = self.pos - self.charge_dir * (self.radius + 16)
            pygame.draw.line(surf, self.color, back, self.pos, 4)
        if self.alive and self.hp < self.max_hp:
            width = self.radius * 2
            bar = pygame.Rect(0, 0, width, 4)
            bar.midbottom = (self.pos.x, self.pos.y - self.radius - 7)
            pygame.draw.rect(surf, (16, 18, 26), bar, border_radius=2)
            fill = bar.copy()
            fill.width = max(2, int(width * self.hp / self.max_hp))
            pygame.draw.rect(surf, (130, 230, 150), fill, border_radius=2)
        if 0 < self.spawn < 0.32 and int(self.lived * 16) % 2 == 0:
            pygame.draw.circle(surf, (255, 255, 255), origin, int(self.radius * scale + 5), 2)
