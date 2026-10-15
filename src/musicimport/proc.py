"""Subprocess helpers.

Every external tool goes through :func:`run` so output can be streamed into a
job log, and so a single place owns env/locale handling.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from typing import Callable, Iterable, Sequence

Log = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


def which(cmd: str) -> str | None:
    if os.path.isabs(cmd):
        return cmd if os.access(cmd, os.X_OK) else None
    return shutil.which(cmd)


def require(cmd: str) -> str:
    path = which(cmd)
    if not path:
        raise FileNotFoundError(f"required tool not found on PATH: {cmd}")
    return path


def run(
    cmd: Sequence[str],
    log: Log | None = None,
    *,
    cwd: str | os.PathLike | None = None,
    input: bytes | str | None = None,
    env: dict | None = None,
    check: bool = True,
    quiet: bool = False,
) -> subprocess.CompletedProcess:
    """Run ``cmd``, streaming stdout+stderr line-by-line to ``log``.

    Uses a C.utf8 locale by default so metaflac/cuetag don't mangle non-ASCII.
    """
    log = log or _noop
    real_env = dict(os.environ)
    real_env.setdefault("LC_ALL", "C.utf8")
    real_env.setdefault("LANG", "C.utf8")
    if env:
        real_env.update(env)

    if not quiet:
        log("$ " + " ".join(str(c) for c in cmd))

    proc = subprocess.Popen(
        [str(c) for c in cmd],
        cwd=cwd,
        env=real_env,
        stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        errors="replace",
    )

    if input is not None:
        if isinstance(input, str):
            input = input.encode()
        assert proc.stdin is not None
        proc.stdin.write(input)
        proc.stdin.close()

    assert proc.stdout is not None
    for line in proc.stdout:
        if not quiet:
            log(line.rstrip("\n"))
    rc = proc.wait()
    if check and rc != 0:
        raise subprocess.CalledProcessError(rc, [str(c) for c in cmd])
    return subprocess.CompletedProcess(cmd, rc)


def capture(cmd: Sequence[str], *, env: dict | None = None) -> str:
    """Run ``cmd`` and return stdout as text (stderr discarded)."""
    real_env = dict(os.environ)
    real_env.setdefault("LC_ALL", "C.utf8")
    real_env.setdefault("LANG", "C.utf8")
    if env:
        real_env.update(env)
    out = subprocess.run(
        [str(c) for c in cmd],
        env=real_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return out.stdout.decode("utf-8", "replace")


def pipe(
    producers: Sequence[Sequence[str]],
    sink: Sequence[str],
    log: Log | None = None,
    *,
    cwd: str | os.PathLike | None = None,
    env: dict | None = None,
    check: bool = True,
) -> int:
    """Emulate ``producer | sink`` (single producer) without a shell."""
    log = log or _noop
    real_env = dict(os.environ)
    real_env.setdefault("LC_ALL", "C.utf8")
    real_env.setdefault("LANG", "C.utf8")
    if env:
        real_env.update(env)

    src = producers[0]
    log("$ " + " ".join(str(c) for c in src) + " | " + " ".join(str(c) for c in sink))

    p1 = subprocess.Popen(
        [str(c) for c in src], cwd=cwd, env=real_env,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    p2 = subprocess.Popen(
        [str(c) for c in sink], cwd=cwd, env=real_env,
        stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace",
    )
    assert p1.stdout is not None
    p1.stdout.close()
    assert p2.stdout is not None
    for line in p2.stdout:
        log(line.rstrip("\n"))
    rc1 = p1.wait()
    rc2 = p2.wait()
    rc = rc2 or rc1
    if check and rc != 0:
        raise subprocess.CalledProcessError(rc, [str(c) for c in sink])
    return rc


class Echo:
    """Minimal log sink that fans out to several callables."""

    def __init__(self, sinks: Iterable[Log]):
        self._sinks = list(sinks)
        self._lock = threading.Lock()

    def __call__(self, msg: str) -> None:
        with self._lock:
            for sink in self._sinks:
                sink(msg)


def listdir(path: str | os.PathLike) -> list[str]:
    """os.listdir that tolerates a missing dir (returns []).

    Uses os.listdir rather than glob deliberately: glob can return empty on
    non-ASCII paths (en-dashes etc.).
    """
    try:
        return os.listdir(path)
    except FileNotFoundError:
        return []
