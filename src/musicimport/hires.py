"""Case D: hi-res (96/192 kHz) detection and downsampling.

Hi-res FLACs are 4-6x the size of a CD rip for no audible gain. This module
only *detects and estimates*; downsampling is a separate, explicit call that
stages 48/24 outputs in a sibling staging dir and never touches originals.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from mutagen.flac import FLAC

from . import proc
from .config import FFMPEG, METAFLAC, STAGING_DIR
from .proc import Log

HIRES_THRESHOLD = 48000


def _flac_files(folder: str | os.PathLike) -> list[Path]:
    folder = Path(folder)
    out = []
    for name in proc.listdir(folder):
        if name.lower().endswith(".flac"):
            out.append(folder / name)
    return sorted(out)


def _int_tag(path: Path, flag: str) -> int | None:
    val = proc.capture([METAFLAC, f"--show-{flag}", str(path)]).strip()
    try:
        return int(val)
    except ValueError:
        return None


def detect(folder: str | os.PathLike) -> dict | None:
    """Return hi-res info for ``folder`` or None if it's all <=48 kHz."""
    files = _flac_files(folder)
    if not files:
        return None

    rates: set[int] = set()
    bps: set[int] = set()
    total_bytes = 0
    total_samples = 0
    hires_files = []
    for f in files:
        sr = _int_tag(f, "sample-rate")
        bd = _int_tag(f, "bps")
        if sr:
            rates.add(sr)
        if bd:
            bps.add(bd)
        if sr and sr > HIRES_THRESHOLD:
            hires_files.append(f.name)
        total_bytes += f.stat().st_size
        ns = proc.capture([METAFLAC, "--show-total-samples", str(f)]).strip()
        try:
            total_samples += int(ns)
        except ValueError:
            pass

    if not rates or not any(r > HIRES_THRESHOLD for r in rates):
        return None

    sr = max(rates)
    est_kbps = None
    if total_samples and sr:
        est_kbps = round(total_bytes * 8 / (total_samples / sr) / 1000)
    # 48/24 target: sample-rate ratio .5 for 96k, .25 for 192k; bit depth 24.
    ratio = 48000 / sr
    reclaim = round(total_bytes * (1 - ratio))
    return {
        "folder": str(folder),
        "sample_rates": sorted(rates),
        "bit_depths": sorted(bps),
        "files": len(files),
        "hires_files": hires_files,
        "total_bytes": total_bytes,
        "est_kbps": est_kbps,
        "target": "48kHz/24bit",
        "est_reclaim_bytes": max(reclaim, 0),
    }


def downsample(folder: str | os.PathLike, dest: str | os.PathLike | None = None,
               log: Log | None = None) -> Path:
    """Convert every FLAC in ``folder`` to 48/24, staged into ``dest``.

    Copies tags with mutagen (survives multiline COMMENT) and copies non-FLAC
    files (cover art) as-is. Returns the staging directory. Originals untouched.
    """
    log = log or (lambda _m: None)
    folder = Path(folder)
    files = _flac_files(folder)
    if not files:
        raise FileNotFoundError(f"no FLAC files in {folder}")

    out_dir = Path(dest) if dest else Path(STAGING_DIR) / folder.name
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"staging 48/24 output in {out_dir}")

    for src in files:
        dst = out_dir / src.name
        proc.run(
            [FFMPEG, "-y", "-v", "error", "-i", str(src),
             "-map", "0", "-c:a", "flac", "-ar", "48000",
             "-sample_fmt", "s32", "-compression_level", "8", str(dst)],
            log=log,
        )
        # mutagen tag copy (metaflac export breaks on multiline COMMENT)
        a = FLAC(str(src))
        b = FLAC(str(dst))
        b.delete()
        for k, v in a.tags.items():
            b[k] = list(v)
        b.save()
        log(f"downsized {src.name}")

    # carry over non-flac files (cover.jpg, logs, cue)
    for name in proc.listdir(folder):
        src = folder / name
        if src.is_file() and src.suffix.lower() != ".flac":
            shutil.copy2(src, out_dir / name)
    return out_dir
