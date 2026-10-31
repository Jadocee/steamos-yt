"""The screen an app starts on, and the interface scale that suits a TV in Game Mode."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Optional

TV_HEIGHT = 720
_SCREEN = re.compile(r"current (\d+) x (\d+)")


def screen_height() -> Optional[int]:
    if not os.environ.get("DISPLAY") or not shutil.which("xrandr"):
        return None
    try:
        output = subprocess.run(
            ["xrandr", "--current"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5, check=False
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _SCREEN.search(output)
    return int(match.group(2)) if match else None


def scale(setting: str, game_mode: bool, height: Optional[int] = None) -> Optional[float]:
    """The interface scale: a number from the settings, or in Game Mode one that shows a 720p-sized layout."""
    value = (setting or "auto").strip().lower()
    if value != "auto":
        try:
            number = float(value)
        except ValueError:
            return None
        return min(max(number, 0.5), 4.0) if number != 1 else None
    if not game_mode:
        return None
    height = screen_height() if height is None else height
    if not height or height < 1000:
        return None
    return round(height / TV_HEIGHT * 4) / 4
