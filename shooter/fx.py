"""Particles, score popups and impact bursts."""

import math
import random

import pygame


class Particle:
    def __init__(self, pos, vel, life, color, size, gravity=0.0, shape="circle"):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.life = life
        self.max_life = max(0.001, life)
        self.color = color
        self.size = size
        self.gravity = gravity
        self.shape = shape

    def update(self, dt):
        self.life -= dt
        self.vel.y += self.gravity * dt
        self.pos += self.vel * dt
        self.vel *= math.exp(-2.4 * dt)
        return self.life > 0

    def draw(self, surf):
        if self.life <= 0:
            return
        fade = self.life / self.max_life
        if self.shape == "ring":
            radius = int(self.size + (1 - fade) * 42)
            if radius > 2:
                pygame.draw.circle(surf, self.color, self.pos, radius, 2)
            return
        if self.shape == "shell":
            rect = pygame.Rect(0, 0, 5, 3)
            rect.center = (int(self.pos.x), int(self.pos.y))
            pygame.draw.rect(surf, self.color, rect, border_radius=1)
            return
        pygame.draw.circle(surf, self.color, self.pos, max(1, int(self.size * fade)))


class Floater:
    def __init__(self, pos, image):
        self.pos = pygame.Vector2(pos)
        self.image = image
        self.life = 0.75
        self.max_life = 0.75

    def update(self, dt):
        self.life -= dt
        self.pos.y -= 40 * dt
        return self.life > 0

    def draw(self, surf):
        self.image.set_alpha(int(255 * max(0.0, self.life / self.max_life)))
        surf.blit(self.image, self.image.get_rect(center=(int(self.pos.x), int(self.pos.y))))


def burst(particles, pos, color, count, speed, life=0.4, size=4):
    for _ in range(count):
        angle = random.random() * math.tau
        spd = random.uniform(speed * 0.3, speed)
        vel = (math.cos(angle) * spd, math.sin(angle) * spd)
        particles.append(Particle(
            pos, vel, random.uniform(life * 0.45, life), color, random.uniform(size * 0.45, size),
        ))


def ring(particles, pos, color, size):
    particles.append(Particle(pos, (0, 0), 0.38, color, size, shape="ring"))
