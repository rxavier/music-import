"""Filesystem + tool configuration.

Defaults match the host layout so the package can also run directly on the
host (dev). Everything is overridable via environment variables, which is how
the container is pointed at bind mounts.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


# --- Media tree --------------------------------------------------------------
MEDIA = _env_path("MUSIC_IMPORT_MEDIA", "/media")
DOWNLOADS = MEDIA / "downloads"

# Release sources, in scan order.
SOURCE_DIRS: tuple[Path, ...] = (
    _env_path("MUSIC_IMPORT_LIDARR", str(DOWNLOADS / "torrents" / "complete" / "lidarr")),
    _env_path("MUSIC_IMPORT_SOULSEEK", str(DOWNLOADS / "soulseek" / "complete")),
)

MUSIC_DIR = _env_path("MUSIC_IMPORT_MUSIC", str(MEDIA / "music"))
STAGING_DIR = _env_path("MUSIC_IMPORT_STAGING", str(MEDIA / "staging"))
WORK_DIR = _env_path(
    "MUSIC_IMPORT_WORK", os.path.join(tempfile.gettempdir(), "music-import")
)

# --- External tools (resolved via PATH unless an absolute path is set) --------
FLACCHECK = os.environ.get("MUSIC_IMPORT_FLACCHECK", "flaccheck")
BEET = os.environ.get("MUSIC_IMPORT_BEET", "beet")

FFMPEG = os.environ.get("MUSIC_IMPORT_FFMPEG", "ffmpeg")
FLAC = os.environ.get("MUSIC_IMPORT_FLAC", "flac")
METAFLAC = os.environ.get("MUSIC_IMPORT_METAFLAC", "metaflac")
SHNSPLIT = os.environ.get("MUSIC_IMPORT_SHNSPLIT", "shnsplit")
CUETAG = os.environ.get("MUSIC_IMPORT_CUETAG", "cuetag")
CUEBREAKPOINTS = os.environ.get("MUSIC_IMPORT_CUEBREAKPOINTS", "cuebreakpoints")
WVUNPACK = os.environ.get("MUSIC_IMPORT_WVUNPACK", "wvunpack")
SEVENZ = os.environ.get("MUSIC_IMPORT_7Z", "7z")

# flaccheck defaults
FLACCHECK_MODE = os.environ.get("MUSIC_IMPORT_FLACCHECK_MODE", "balanced")
FLACCHECK_WORKERS = int(os.environ.get("MUSIC_IMPORT_FLACCHECK_WORKERS", "4"))

# --- beets -------------------------------------------------------------------
BEETSDIR = os.environ.get("BEETSDIR")  # beets honours this natively

# --- Web ---------------------------------------------------------------------
HOST = os.environ.get("MUSIC_IMPORT_HOST", "127.0.0.1")
PORT = int(os.environ.get("MUSIC_IMPORT_PORT", "8318"))

# Audio extensions we care about.
LOSSLESS_EXT = {".flac", ".wav", ".aif", ".aiff", ".alac", ".ape", ".wv", ".shn"}
