"""PTY plumbing for an interactive ``beet import``.

beets' importer is a curses-style prompt, so it needs a real terminal. We run
it under a pseudo-terminal and bridge that to an xterm.js websocket in the web
layer.
"""
from __future__ import annotations

import fcntl
import os
import pty
import struct
import subprocess
import termios

from . import proc
from .config import BEET


def build_env() -> dict:
    env = dict(os.environ)
    env.setdefault("TERM", "xterm-256color")
    env.setdefault("LC_ALL", "C.utf8")
    env.setdefault("LANG", "C.utf8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def spawn(path: str, *, cwd: str | None = None,
          args: list[str] | None = None) -> tuple[int, subprocess.Popen]:
    """Start ``beet import <path>`` under a PTY. Returns (master_fd, proc)."""
    beet = proc.require(BEET)
    cmd = [beet, "import", *(args or []), str(path)]
    master, slave = pty.openpty()
    env = build_env()
    proc_ = subprocess.Popen(
        cmd,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=cwd,
        env=env,
        close_fds=True,
        preexec_fn=os.setsid,
    )
    os.close(slave)
    return master, proc_


def set_winsize(fd: int, rows: int, cols: int) -> None:
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ,
                    struct.pack("HHHH", rows, cols, 0, 0))
    except OSError:
        pass


def read(fd: int, size: int = 4096) -> bytes:
    try:
        return os.read(fd, size)
    except OSError:
        return b""


def write(fd: int, data: bytes) -> None:
    try:
        os.write(fd, data)
    except OSError:
        pass


def close(fd: int, p: subprocess.Popen) -> None:
    try:
        os.close(fd)
    except OSError:
        pass
    if p.poll() is None:
        try:
            os.killpg(os.getpgid(p.pid), 15)
        except (ProcessLookupError, PermissionError):
            try:
                p.terminate()
            except Exception:  # noqa: BLE001
                pass
