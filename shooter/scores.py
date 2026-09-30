"""Best score remembered on this computer."""

import os
from pathlib import Path


def high_score_path():
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) / "MiniShooter" if base else Path.home() / ".mini-shooter"
    return root / "best.txt"


def read_high_score():
    try:
        return max(0, int(high_score_path().read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        return 0


def write_high_score(score):
    path = high_score_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(int(score)), encoding="utf-8")
