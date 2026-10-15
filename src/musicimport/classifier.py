"""Classify a release folder by its *shape* (what kind of source it holds).

Mirrors step 2 of the music-import skill. Pure filesystem inspection — no
decoding, no tool calls.
"""
from __future__ import annotations

import os
from pathlib import Path

LOSSY_EXT = {".mp3", ".m4a", ".aac", ".opus", ".ogg", ".wma", ".mpc"}


def _walk_files(folder: Path) -> list[Path]:
    out = []
    for root, _dirs, files in os.walk(folder):
        for name in files:
            out.append(Path(root) / name)
    return out


def classify(folder: str | os.PathLike) -> dict:
    folder = Path(folder)
    files = _walk_files(folder)
    exts = {}
    for f in files:
        exts[f.suffix.lower()] = exts.get(f.suffix.lower(), 0) + 1

    flacs = [f for f in files if f.suffix.lower() == ".flac"]
    apes = [f for f in files if f.suffix.lower() == ".ape"]
    wvs = [f for f in files if f.suffix.lower() == ".wv"]
    isos = [f for f in files
            if f.suffix.lower() == ".iso"
            or f.name.lower().endswith((".wv.iso", ".wv.iso.wv"))]
    has_cue = any(f.suffix.lower() == ".cue" for f in files)
    lossy = [f for f in files if f.suffix.lower() in LOSSY_EXT]

    if wvs or isos:
        return {
            "shape": "wv_iso",
            "label": "WavPack / ISO image",
            "action": "convert_wv",
            "action_label": "Extract ISO + split WavPack",
            "counts": {"wv": len(wvs), "iso": len(isos)},
        }
    if apes and has_cue:
        return {
            "shape": "ape_cue",
            "label": "APE image + cue",
            "action": "convert_ape",
            "action_label": "Convert APE -> FLAC + split",
            "counts": {"ape": len(apes)},
        }
    if has_cue and len(flacs) == 1:
        return {
            "shape": "flac_cue",
            "label": "FLAC image + cue",
            "action": "split",
            "action_label": "Split into tracks",
            "counts": {"flac": 1},
        }
    if len(flacs) >= 2:
        # Per-track FLACs. A leftover cue (e.g. bonus tracks from a deluxe
        # edition) does not make this a single-disc image.
        return {
            "shape": "split_tracks",
            "label": "Per-track FLAC (already split)",
            "action": "import",
            "action_label": "Ready to import",
            "counts": {"flac": len(flacs)},
        }
    if len(flacs) == 1 and not has_cue:
        return {
            "shape": "flac_no_cue",
            "label": "Single FLAC, no cue",
            "action": "manual",
            "action_label": "No cue sheet — manual",
            "counts": {"flac": 1},
        }
    if lossy and not flacs:
        return {
            "shape": "lossy",
            "label": "Lossy source (not lossless)",
            "action": "skip",
            "action_label": "Skip (lossy)",
            "counts": {"lossy": len(lossy)},
        }
    if not files:
        return {
            "shape": "empty",
            "label": "Empty",
            "action": "skip",
            "action_label": "Nothing here",
            "counts": {},
        }
    return {
        "shape": "other",
        "label": "Other / unrecognised",
        "action": "manual",
        "action_label": "Manual",
        "counts": {e: c for e, c in sorted(exts.items()) if e},
    }
