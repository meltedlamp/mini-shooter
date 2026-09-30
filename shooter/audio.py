"""Short synthesized shots, hits and a quiet pulse loop. No asset files."""

import math
import random
from array import array

import pygame


RATE = 44100


def _sound(samples, volume):
    buf = array("h", (max(-32767, min(32767, int(s * volume * 32767))) for s in samples))
    return pygame.mixer.Sound(buffer=buf)


def _blip(freq, duration, volume, wave="square"):
    n = max(1, int(RATE * duration))
    buf = []
    for i in range(n):
        t = i / RATE
        if wave == "square":
            s = 1.0 if int(t * freq * 2) % 2 == 0 else -1.0
        else:
            s = math.sin(math.tau * freq * t)
        env = min(1.0, i / 12) * (1 - i / n)
        buf.append(s * env)
    return _sound(buf, volume)


def _noise(duration, volume, decay, seed):
    n = max(1, int(RATE * duration))
    rng = random.Random(seed)
    buf = []
    for i in range(n):
        env = math.exp(-decay * i / RATE) * min(1.0, i / 10)
        buf.append(rng.uniform(-1, 1) * env)
    return _sound(buf, volume)


def _music():
    seconds = 2.0
    n = int(RATE * seconds)
    buf = []
    for i in range(n):
        t = i / RATE
        beat = t % 0.5
        env = math.exp(-beat * 7.5)
        s = math.sin(math.tau * 55 * t) * 0.55 * env
        s += math.sin(math.tau * 110 * t) * 0.18 * env
        s += math.sin(math.tau * 82.5 * t) * 0.06
        buf.append(s)
    sound = _sound(buf, 0.22)
    return sound


def _heal():
    step = int(RATE * 0.07)
    buf = []
    for freq in (660, 880):
        for i in range(step):
            env = min(1.0, i / 8) * (1 - i / step)
            buf.append(math.sin(math.tau * freq * i / RATE) * env)
    return _sound(buf, 0.28)


def _wave():
    step = int(RATE * 0.06)
    buf = []
    for freq in (523, 659, 784):
        for i in range(step):
            env = min(1.0, i / 6) * (1 - i / step)
            s = 1.0 if int(i * freq / RATE * 2) % 2 == 0 else -1.0
            buf.append(s * env)
    return _sound(buf, 0.24)


class Audio:
    def __init__(self):
        self.muted = False
        self.ok = False
        self.music = None
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(RATE, -16, 1, 512)
            self.sounds = {
                "shoot": _blip(920, 0.035, 0.18),
                "hit": _noise(0.06, 0.28, 28, 2),
                "pop": _blip(210, 0.09, 0.32),
                "boom": _noise(0.28, 0.4, 10, 5),
                "hurt": _blip(180, 0.14, 0.34, wave="sine"),
                "dash": _noise(0.09, 0.22, 22, 9),
                "heal": _heal(),
                "wave": _wave(),
            }
            self.music = _music()
            self.music.play(-1)
            self.ok = True
        except pygame.error:
            self.sounds = {}
            self.ok = False

    def play(self, name):
        if self.muted or not self.ok:
            return
        sound = self.sounds.get(name)
        if sound is not None:
            sound.play()

    def toggle(self):
        self.muted = not self.muted
        if not self.ok:
            return self.muted
        if self.muted:
            pygame.mixer.pause()
        else:
            pygame.mixer.unpause()
        return self.muted
