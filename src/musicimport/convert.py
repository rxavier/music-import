"""Case A (APE image + cue) and Case C (WavPack / ISO image) conversion.

Both produce per-track FLACs in the release folder (Case A) or a sibling
``[FLAC]`` folder (Case C) and never touch the original files.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import proc, splitrename
from .config import FFMPEG, SEVENZ, SHNSPLIT, WORK_DIR
from .proc import Log


def _files_by_ext(folder: Path, *exts: str) -> list[Path]:
    want = {e.lower() for e in exts}
    return sorted(f for f in (folder / n for n in proc.listdir(folder))
                  if f.suffix.lower() in want)


def convert_ape(folder: str | os.PathLike, log: Log | None = None) -> list[Path]:
    """Case A: convert ``X.ape`` to ``X.flac``, then split via ``X.cue``."""
    log = log or (lambda _m: None)
    folder = Path(folder)
    cues = {Path(n).stem for n in proc.listdir(folder) if n.lower().endswith(".cue")}
    for ape in _files_by_ext(folder, ".ape"):
        base = ape.stem
        if base not in cues:
            continue
        flac = folder / f"{base}.flac"
        proc.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(ape),
             "-c:a", "flac", "-compression_level", "8", str(flac), "-y"],
            log=log,
        )
        return splitrename.split(base, folder, log)
    raise FileNotFoundError(f"no matching .ape/.cue pair in {folder}")


def _find_iso(folder: Path) -> Path | None:
    for name in proc.listdir(folder):
        low = name.lower()
        if low.endswith((".wv.iso", ".wv.iso.wv", ".iso")) or low.endswith(".wv"):
            return folder / name
    return None


def convert_wv(folder: str | os.PathLike, log: Log | None = None) -> Path:
    """Case C: extract an ISO/WavPack release and split it into FLAC tracks.

    Returns the sibling ``[FLAC]`` output folder.
    """
    log = log or (lambda _m: None)
    folder = Path(folder)
    archive = _find_iso(folder)
    if archive is None:
        raise FileNotFoundError(f"no .wv/.iso archive in {folder}")

    tmp = Path(WORK_DIR) / folder.name
    tmp.mkdir(parents=True, exist_ok=True)
    proc.run([SEVENZ, "x", f"-o{tmp}", str(archive), "-y"], log=log, quiet=False)

    inner_wv = next((f for f in tmp.rglob("*") if f.suffix.lower() == ".wv"), None)
    inner_cue = next((f for f in tmp.rglob("*") if f.suffix.lower() == ".cue"), None)
    if inner_wv is None or inner_cue is None:
        raise RuntimeError(f"extracted ISO missing .wv or .cue (see {tmp})")

    out = folder.parent / f"{folder.name} [FLAC]"
    out.mkdir(parents=True, exist_ok=True)

    work_cue = tmp / f"{folder.name}.work.cue"
    splitrename.normalize_cue(inner_cue, work_cue, log)
    proc.run(
        [SHNSPLIT, "-f", str(work_cue), "-o", "flac", "-t", "%02n",
         str(inner_wv), "-d", str(out)],
        log=log,
    )
    splitrename.tag_tracks(out, work_cue, splitrename.track_files(out), log)
    tracks = splitrename.rename_tracks(out, log)

    cover = next((f for f in tmp.rglob("*")
                  if f.suffix.lower() in (".jpg", ".jpeg", ".png")
                  and "front" in f.name.lower()), None)
    if cover:
        shutil.copy2(cover, out / "cover.jpg")
        log(f"copied cover art -> {out.name}/cover.jpg")

    log(f"produced {len(tracks)} track(s) in {out}")
    return out
