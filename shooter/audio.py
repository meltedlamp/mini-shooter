"""Shots, hits, and a small tune for each map. No asset files."""

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


def _silence(seconds):
    return [0.0] * int(RATE * seconds)


def _add_tone(buf, start, dur, freq, volume, decay, partials=(1.0,)):
    begin = int(start * RATE)
    count = int(dur * RATE)
    scale = sum(abs(p) for p in partials) or 1.0
    for i in range(count):
        at = begin + i
        if at < 0 or at >= len(buf):
            break
        u = i / RATE
        env = min(1.0, i / 8) * math.exp(-decay * u)
        sample = 0.0
        for n, amp in enumerate(partials, start=1):
            sample += math.sin(math.tau * freq * n * u) * amp
        buf[at] += sample / scale * env * volume


def _deduction():
    """Clear, cool bells. Open floor, nothing in the way."""
    buf = _silence(4.0)
    for hit in (0.0, 2.0):
        _add_tone(buf, hit, 0.7, 110.0, 0.22, 3.2)
    notes = (
        (0.00, 880.00),
        (0.50, 659.25),
        (1.00, 523.25),
        (1.50, 659.25),
        (2.00, 783.99),
        (2.50, 659.25),
        (3.00, 587.33),
        (3.50, 523.25),
    )
    for start, freq in notes:
        _add_tone(buf, start, 0.42, freq, 0.16, 5.5)
        _add_tone(buf, start, 0.03, 1860.0, 0.035, 40)
    return _sound(buf, 0.28)


def _kiln():
    """Low pulse and a heated half-step line. Lava underfoot."""
    buf = _silence(4.0)
    for step in range(8):
        _add_tone(buf, step * 0.5, 0.28, 49.0, 0.34, 9.0, (1.0, 0.35))
    notes = (
        (0.00, 164.81),
        (0.50, 174.61),
        (1.00, 164.81),
        (1.50, 146.83),
        (2.00, 123.47),
        (2.50, 146.83),
        (3.00, 164.81),
        (3.50, 174.61),
    )
    for start, freq in notes:
        _add_tone(buf, start, 0.36, freq, 0.2, 6.0, (1.0, 0.22, 0.08))
    return _sound(buf, 0.3)


def _veil():
    """Slow mist. No beat, just a chord that breathes and joins cleanly."""
    seconds = 4.0
    buf = _silence(seconds)
    # Integer cycles so the loop point does not click.
    layers = (
        (220.0, 0.10, 1),
        (262.0, 0.07, 2),
        (330.0, 0.06, 1),
        (392.0, 0.035, 3),
        (660.0, 0.02, 1),
    )
    n = len(buf)
    for freq, volume, tremolo in layers:
        for i in range(n):
            t = i / RATE
            breath = 0.82 + 0.18 * math.sin(math.tau * tremolo * t / seconds)
            buf[i] += math.sin(math.tau * freq * t) * volume * breath
    return _sound(buf, 0.34)


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
        self.bed = None
        self.held = False
        self.music = None
        self.beds = {}
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(RATE, -16, 1, 512)
            pygame.mixer.set_reserved(1)
            self.music = pygame.mixer.Channel(0)
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
            self.builders = {
                "deduction": _deduction,
                "kiln": _kiln,
                "veil": _veil,
            }
            self.beds = {}
            self.ok = True
        except pygame.error:
            self.sounds = {}
            self.ok = False

    def set_bed(self, name):
        if name == self.bed and not self.held:
            return
        self.bed = name
        if not self.ok or self.music is None:
            return
        self.music.stop()
        if not name:
            self.held = False
            return
        sound = self.beds.get(name)
        if sound is None and name in self.builders:
            sound = self.builders[name]()
            self.beds[name] = sound
        if sound is None or self.muted:
            self.held = True
            return
        self.held = False
        self.music.play(sound, loops=-1)

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
            if self.held and self.music is not None:
                sound = self.beds.get(self.bed)
                if sound is not None:
                    self.music.play(sound, loops=-1)
                self.held = False
        return self.muted
