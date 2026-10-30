"""Terminal output and prompts shared by the commands."""

from __future__ import annotations

import os
import sys

quiet = False
assume_yes = False

_COLOUR = sys.stderr.isatty() and not os.environ.get("NO_COLOR")


def _paint(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOUR else text


class Abort(RuntimeError):
    """A failure to report as ``error: <message>`` before exiting."""


def log(message: str) -> None:
    if not quiet:
        print(f"{_paint('34', '==>')} {_paint('1', message)}", file=sys.stderr)


def info(message: str) -> None:
    if not quiet:
        print(f"    {message}", file=sys.stderr)


def ok(message: str) -> None:
    if not quiet:
        print(f"{_paint('32', ' ✓')}  {message}", file=sys.stderr)


def warn(message: str) -> None:
    print(f"{_paint('33', 'warning:')} {message}", file=sys.stderr)


def error(message: str) -> None:
    print(f"{_paint('31', 'error:')} {message}", file=sys.stderr)


def bold(text: str) -> str:
    return _paint("1", text)


def confirm(question: str, default: bool = False) -> bool:
    """Ask a yes/no question on the terminal; without one, return ``default``."""
    if assume_yes:
        return True
    try:
        with open("/dev/tty", "w", encoding="utf-8") as output, open("/dev/tty", encoding="utf-8") as answers:
            output.write(f"{_paint('33', '?')} {question} {'[Y/n]' if default else '[y/N]'} ")
            output.flush()
            reply = answers.readline().strip().lower()
    except OSError:
        return default
    return default if not reply else reply in ("y", "yes")
