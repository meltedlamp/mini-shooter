"""Best score and map preference remembered on this computer."""

import os
from pathlib import Path


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
    best = 0
    for folder in _save_dirs():
        value = _read_int(folder / "best.txt")
        if value is not None:
            best = max(best, value)
    return max(0, best)


def write_high_score(score):
    text = str(max(0, int(score)))
    for folder in _save_dirs():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "best.txt").write_text(text, encoding="utf-8")
            return
        except OSError:
            continue
    raise OSError("could not save the best score")


def read_map_open(default=False):
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
    for folder in _save_dirs():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "map.txt").write_text(text, encoding="utf-8")
            return
        except OSError:
            continue
