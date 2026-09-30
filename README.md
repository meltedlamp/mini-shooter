# Mini Shooter

A tiny original arena shooter written in Python with [Pygame](https://www.pygame.org/).
Move with the keyboard, aim with the mouse, and hold the button to fire. Waves of
enemies close in across a small arena. Dash through their shots, duck behind crates,
and grab hearts before the next wave starts.

![Mini Shooter gameplay](screenshots/fight.png)

## Screenshots

| Title | In the arena | Game over |
| --- | --- | --- |
| ![Title screen](screenshots/title.png) | ![Arena fight](screenshots/fight.png) | ![Game over](screenshots/over.png) |

## Features

- **Aim and shoot**: the gun tracks the cursor, kicks back, and throws a muzzle flash. Bullets leave a short trail.
- **Dash**: Shift bursts you across the floor and leaves afterimages. You slip through enemy shots while dashing.
- **Three enemies**: orange grunts that chase, purple shooters that hang back and fire, and big red brutes that telegraph a charge with a line, then rush.
- **Cover**: wooden crates stop you and stop bullets. A brute that charges into one slams to a halt.
- **Hearts**: you start with 5. Brutes drop a heart. Picking one up heals you, or scores 50 points if you are already full.
- **Waves**: each clear pays a bonus and the next wave brings more enemies. Shooters show up from wave 2, and a brute joins every third wave.
- **Juice**: dust when you run, sparks and rings when something dies, floating scores, a short freeze on a brute kill, and screen shake.
- **Best score** is remembered on this computer and shown on the title screen.
- **Quiet pulse music** and little synthesized shots, hits, and explosions. Press `M` to mute.
- **No asset files.** The characters, crates, particles, music, and sound effects are all drawn and synthesized in code.

## Getting started

You need **Python 3.8+**.

```bash
git clone https://github.com/yugdogra0/mini-shooter.git
cd mini-shooter
pip install -r requirements.txt
python game.py
```

## Controls

| Action | Keys / mouse |
| --- | --- |
| Move | `W` `A` `S` `D` or the arrow keys |
| Aim | Mouse |
| Shoot | Hold the left mouse button |
| Dash | `Shift` |
| Start / play again | Click **Play** or **Again** (or press `Enter` or `Space`) |
| Pause | `Esc`, then **Resume** or **Title** |
| Mute / unmute | `M` |
| Quit | Click **Exit** (or press `Esc` on the title screen) |

## How to play

- Clear every enemy in the wave. A banner announces the next one, and you get a moment to move before they spawn at the edges.
- Grunts walk straight at you. Two shots stop one. Touching an enemy costs a heart.
- Shooters keep their distance and fire slow orange shots. Crates block those shots, so step behind one instead of eating the bullet.
- A brute pauses, draws a line toward you, then charges faster than you can run. Sidestep or dash. It takes a lot of shots, shakes the screen when it goes down, and drops a heart.
- After a hit you blink and cannot be hurt again for a short moment. Use that to get out of a pile of grunts.
- The dash meter at the top right refills after each dash. It is the reliable way through a charge or a tight volley.
- Lose all 5 hearts and the run ends. Your best score stays on the title screen.

## Tweaking the game

Feel settings live in `shooter/settings.py`:

```python
PLAYER_SPEED = 245         # how fast you run
DASH_SPEED = 640           # burst speed
DASH_TIME = 0.16           # how long a dash lasts
DASH_COOLDOWN = 0.82       # seconds before you can dash again
FIRE_COOLDOWN = 0.14       # delay between shots
PLAYER_BULLET_SPEED = 700
ENEMY_BULLET_SPEED = 255
MAX_HEARTS = 5
HURT_TIME = 0.95           # invincible time after a hit
```

Enemy health, speed, size, and points are the `STATS` table in `shooter/actors.py`.
Wave size is `wave_kinds()` in `shooter/game.py`: wave 1 is three grunts, later waves add shooters, and every third wave from wave 3 adds a brute.

## Project structure

```
mini-shooter/
├── game.py              # launcher: python game.py
├── shooter/             # the game package (also runs with: python -m shooter)
│   ├── game.py          # arena loop: waves, collisions, menus, drawing
│   ├── actors.py        # player, enemies, bullets, hearts, and their animation
│   ├── fx.py            # sparks, rings, shell casings, floating scores
│   ├── audio.py         # synthesized shots, hits, and the pulse loop
│   ├── settings.py      # window size, colours, and tuning knobs
│   └── scores.py        # the best score saved on this computer
├── requirements.txt     # pygame dependency
├── screenshots/         # images used in this README
└── README.md
```
