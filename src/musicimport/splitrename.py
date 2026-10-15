"""Python port of the ``splitrename`` zsh function.

Split a ``X.flac`` + ``X.cue`` image into per-track FLACs and rename them
``NN Title.flac`` using the TITLE tag. Produces new files in the release
folder; never touches the source image. The zsh original stays in ~/.zshrc.

The helpers here (:func:`normalize_cue`, :func:`tag_tracks`,
:func:`rename_tracks`) are also reused by the APE/WavPack paths.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import proc
from .config import CUEBREAKPOINTS, CUETAG, METAFLAC, SHNSPLIT
from .proc import Log

TRACK_RE = re.compile(r"^\d{2}\.flac$")


def normalize_cue(src: Path, dst: Path, log: Log) -> None:
    """Strip UTF-8 BOM, convert CRLF -> LF, ensure a trailing newline."""
    data = src.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        log(f"Stripping UTF-8 BOM from {src.name}")
        data = data[3:]
    if b"\r" in data:
        log(f"Converting CRLF to LF in {src.name}")
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if not data.endswith(b"\n"):
        data += b"\n"
    dst.write_bytes(data)


def track_files(folder: Path) -> list[Path]:
    return sorted(
        folder / name for name in proc.listdir(folder) if TRACK_RE.match(name)
    )


def tag_tracks(folder: Path, cue: Path, tracks: list[Path], log: Log) -> None:
    """Tag ``tracks`` from the cue sheet with cuetag."""
    if not tracks:
        raise RuntimeError("no [0-9][0-9].flac tracks to tag")
    proc.run(
        [CUETAG, str(cue), *[str(t) for t in tracks]],
        log=log, cwd=folder, env={"LC_ALL": "C.utf8"},
    )


def rename_tracks(folder: Path, log: Log) -> list[Path]:
    """Rename ``NN.flac`` -> ``NN Title.flac`` from the TITLE tag."""
    out: list[Path] = []
    for f in track_files(folder):
        title = proc.capture([METAFLAC, "--show-tag=TITLE", str(f)]).strip()
        title = title[len("TITLE="):] if title.startswith("TITLE=") else title
        track = proc.capture([METAFLAC, "--show-tag=TRACKNUMBER", str(f)]).strip()
        track = track[len("TRACKNUMBER="):] if track.startswith("TRACKNUMBER=") else track
        try:
            num = f"{int(track):02d}"
        except ValueError:
            num = f.name[:2]
        clean_title = title.replace("/", "-").rstrip()
        target = folder / f"{num} {clean_title}.flac"
        if target != f and not target.exists():
            os.rename(f, target)
            out.append(target)
        else:
            out.append(f)
    return out


def split(base: str, folder: str | os.PathLike | None = None,
          log: Log | None = None) -> list[Path]:
    """Split ``<folder>/<base>.flac`` driven by ``<base>.cue``."""
    log = log or (lambda _m: None)
    folder = Path(folder) if folder else Path(".")
    flac = folder / f"{base}.flac"
    cue = folder / f"{base}.cue"

    if not flac.is_file() or not cue.is_file():
        raise FileNotFoundError(f"missing {flac.name} or {cue.name}")

    work = folder / f"{base}.work.cue"
    normalize_cue(cue, work, log)
    try:
        proc.pipe(
            [[CUEBREAKPOINTS, str(work)]],
            [SHNSPLIT, "-o", "flac", "-t", "%02n", str(flac)],
            log=log, cwd=folder,
        )
        tag_tracks(folder, work, track_files(folder), log)
    finally:
        work.unlink(missing_ok=True)

    out = rename_tracks(folder, log)
    log(f"split + renamed {len(out)} track(s)")
    return out


def split_release(folder: str | os.PathLike, log: Log | None = None) -> list[Path]:
    """Locate the single ``X.flac``/``X.cue`` pair in ``folder`` and split it."""
    log = log or (lambda _m: None)
    folder = Path(folder)
    flacs = [n for n in proc.listdir(folder) if n.lower().endswith(".flac")]
    cues = {Path(n).stem for n in proc.listdir(folder) if n.lower().endswith(".cue")}
    for name in sorted(flacs):
        base = Path(name).stem
        if base in cues:
            return split(base, folder, log)
    raise FileNotFoundError(f"no matching .flac/.cue pair in {folder}")
