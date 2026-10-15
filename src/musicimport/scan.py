"""Scan the download sources and describe each release folder.

A release is a folder that directly contains audio files. Folders without
direct audio are transparent (descended into), so service dirs (lidarr/),
scan/artwork folders, and arbitrary nesting on the way down are handled
without hardcoded names. Exception: a folder whose audio-bearing children are
all disc-named (CD1/CD2/Disc 2/...) is treated as a single multi-disc release.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import proc
from .classifier import classify
from .config import SOURCE_DIRS

AUDIO_EXT = {
    ".flac", ".ape", ".wv", ".wav", ".aif", ".aiff", ".alac", ".shn",
    ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".mpc",
}
DISC_RE = re.compile(r"^(cd|disc|disk)\s*0*\d+$", re.IGNORECASE)


def _has_audio(folder: Path) -> bool:
    return any(Path(n).suffix.lower() in AUDIO_EXT for n in proc.listdir(folder))


def _child_dirs(folder: Path) -> list[Path]:
    out = []
    for name in sorted(proc.listdir(folder)):
        if name.startswith("."):
            continue
        p = folder / name
        if p.is_dir() and not p.is_symlink():
            out.append(p)
    return out


def _collect(folder: Path) -> list[Path]:
    """Return the release folders at or below ``folder``."""
    if _has_audio(folder):
        return [folder]
    sub: list[Path] = []
    for child in _child_dirs(folder):
        sub.extend(_collect(child))
    # Multi-disc: every release found sits directly under us and is disc-named.
    if (len(sub) >= 2
            and all(r.parent == folder and DISC_RE.match(r.name) for r in sub)):
        return [folder]
    return sub


def _release_dirs() -> list[tuple[str, Path]]:
    seen: set[Path] = set()
    out: list[tuple[str, Path]] = []
    for src in SOURCE_DIRS:
        if not src.is_dir():
            continue
        for p in _collect(src):
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            out.append((str(src), p))
    return out


def _folder_size(folder: Path) -> tuple[int, int]:
    total = 0
    count = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
                count += 1
            except OSError:
                pass
    return total, count


def releases() -> list[dict]:
    out = []
    for source, folder in _release_dirs():
        shape = classify(folder)
        size, count = _folder_size(folder)
        out.append({
            "path": str(folder),
            "name": folder.name,
            "source": source,
            "size_bytes": size,
            "file_count": count,
            **shape,
        })
    return out


def release(path: str | os.PathLike) -> dict:
    folder = Path(path)
    shape = classify(folder)
    size, count = _folder_size(folder)
    return {
        "path": str(folder),
        "name": folder.name,
        "size_bytes": size,
        "file_count": count,
        **shape,
    }
