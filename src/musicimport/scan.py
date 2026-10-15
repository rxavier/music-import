"""Scan the download sources and describe each release folder."""
from __future__ import annotations

import os
from pathlib import Path

from . import proc
from .classifier import classify
from .config import SOURCE_DIRS


def _release_dirs() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for src in SOURCE_DIRS:
        if not src.is_dir():
            continue
        for name in sorted(proc.listdir(src)):
            p = src / name
            if not p.is_dir():
                continue
            if name == "lidarr":  # soulseek nests a lidarr/ subfolder
                for sub in sorted(proc.listdir(p)):
                    sp = p / sub
                    if sp.is_dir():
                        out.append((str(src), sp))
            else:
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
