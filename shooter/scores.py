"""Best score and map preference remembered on this computer."""

import os
import sys
from pathlib import Path

_BEST_KEY = "mini-shooter-best"
_MAP_KEY = "mini-shooter-map"


def _browser():
    return sys.platform == "emscripten"


def _storage():
    import platform

    return platform.window.localStorage


def _save_dirs():
    dirs = []
    base = os.environ.get("LOCALAPPDATA")
    if base:
        dirs.append(Path(base) / "MiniShooter")
    dirs.append(Path.home() / ".mini-shooter")
    return dirs


def _read_int(path):
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def read_high_score():
    if _browser():
        try:
            return max(0, int(_storage().getItem(_BEST_KEY)))
        except (TypeError, ValueError, AttributeError):
            return 0
    best = 0
    for folder in _save_dirs():
        value = _read_int(folder / "best.txt")
        if value is not None:
            best = max(best, value)
    return max(0, best)


def note_arcade(game, score, note=""):
    """Leave this run for Melted Arcade, on the name signed in there."""
    if not _browser():
        return
    try:
        import json
        import time

        storage = _storage()
        player = str(storage.getItem("melted-arcade-player") or "").strip()
        score = max(0, int(score))
        if not player or score <= 0:
            return
        raw = storage.getItem("melted-arcade-slips") or "[]"
        try:
            slips = json.loads(str(raw))
        except ValueError:
            slips = []
        if not isinstance(slips, list):
            slips = []
        slips.append({
            "game": str(game),
            "score": score,
            "player": player,
            "note": "win" if note == "win" else "",
            "at": int(time.time() * 1000),
        })
        storage.setItem("melted-arcade-slips", json.dumps(slips[-40:]))
    except Exception:
        return


def write_high_score(score):
    text = str(max(0, int(score)))
    if _browser():
        try:
            _storage().setItem(_BEST_KEY, text)
        except AttributeError:
            pass
        return
    for folder in _save_dirs():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "best.txt").write_text(text, encoding="utf-8")
            return
        except OSError:
            continue
    raise OSError("could not save the best score")


def read_map_open(default=False):
    if _browser():
        try:
            flag = _storage().getItem(_MAP_KEY)
        except AttributeError:
            return default
        if flag in ("0", "1"):
            return flag == "1"
        return default
    for folder in _save_dirs():
        try:
            flag = (folder / "map.txt").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if flag in ("0", "1"):
            return flag == "1"
    return default


def write_map_open(open_):
    text = "1" if open_ else "0"
    if _browser():
        try:
            _storage().setItem(_MAP_KEY, text)
        except AttributeError:
            pass
        return
    for folder in _save_dirs():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "map.txt").write_text(text, encoding="utf-8")
            return
        except OSError:
            continue
