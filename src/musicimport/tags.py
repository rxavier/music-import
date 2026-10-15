"""Python port of ``clean-music-tags``.

Strips non-standard tag junk (ripper watermarks, Discogs/Tidal/AccurateRip
leftovers, binary PRIV blobs) from FLAC/MP3, keeping core beets/MusicBrainz
tags. Never deletes files; only rewrites tags.

Exposes :func:`plan` (dry run -> {file: [tags]}) and :func:`apply`.
"""
from __future__ import annotations

import collections
import os
from typing import Iterable

from mutagen import File

# --- FLAC/Vorbis-comment keep-list (lowercase) -------------------------------
FLAC_KEEP = {
    "title", "artist", "album", "albumartist", "album artist",
    "album_artist", "albumartists", "albumartist_credit",
    "albumartists_credit", "albumartists_sort", "albumartistsort",
    "album artist credit",
    "artist_credit", "artistcredit", "artists", "artists_credit",
    "artists_sort", "artistsort", "artistsorts",
    "tracknumber", "track", "trackc", "tracktotal", "totaltracks",
    "discnumber", "disc", "discc", "disctotal", "totaldiscs", "discsubtitle",
    "date", "originaldate", "originalyear", "year",
    "genre", "grouping", "compilation", "itunesadvisory", "mediatype",
    "releasetype", "releasestatus", "releasecountry", "language", "script",
    "subtitle", "media",
    "composer", "composersort", "composers", "composers_credit", "lyricist",
    "conductor", "arranger", "engineer", "mixer", "producer", "remixer",
    "remixers", "performer", "ensemble", "involvedpeople", "credits",
    "label", "publisher", "organization", "catalognumber", "barcode", "isrc",
    "copyright", "asin", "work",
    "lyrics", "unsyncedlyrics", "bpm",
    "encodedby", "encoded-by", "encoded by", "encoder", "encoder settings",
    "replaygain_reference_loudness", "replaygain_track_gain",
    "replaygain_track_peak", "replaygain_album_gain", "replaygain_album_peak",
    "dynamic range", "album dynamic range", "dranalysed",
}
FLAC_KEEP_PREFIXES = ("musicbrainz_", "acoustid_")

ID3_KEEP = {
    "TIT2", "TPE1", "TPE2", "TALB", "TRCK", "TPOS", "TCON", "TCOM", "TCMP",
    "TLAN", "TMED", "TBPM", "TKEY", "TPUB", "TSRC", "TSSE", "TSOP", "TSO2",
    "TDRC", "TDOR", "TDAT", "TYER", "TFLT", "USLT", "APIC", "UFID",
}
TXXX_KEEP = (
    "musicbrainz", "acoustid", "barcode", "catalognumber", "label",
    "originalyear", "originaldate", "releasecountry", "releasetype",
    "releasestatus", "language", "script", "media", "asin",
    "artist", "albumartist",
)


def norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


_FLAC_KEEP = {norm(k) for k in FLAC_KEEP}
_FLAC_KEEP_PREFIXES = tuple(norm(p) for p in FLAC_KEEP_PREFIXES)


def flac_wanted(key: str) -> bool:
    k = norm(key)
    return k in _FLAC_KEEP or k.startswith(_FLAC_KEEP_PREFIXES)


def _junk_for(audio, ext: str) -> list[str]:
    if ext == ".flac":
        return [k for k in audio.tags.keys() if not flac_wanted(k)]
    to_del = []
    for k in audio.tags.keys():
        base = k.split(":")[0].upper()
        if base in ID3_KEEP:
            continue
        if base == "TXXX":
            d = norm(audio.tags[k].desc)
            if any(d.startswith(pr) for pr in TXXX_KEEP):
                continue
        to_del.append(k)
    return to_del


def _audio_files(path: str | os.PathLike) -> Iterable[str]:
    if os.path.isfile(path):
        yield str(path)
        return
    for root, _dirs, files in os.walk(path):
        for name in files:
            if os.path.splitext(name)[1].lower() in (".flac", ".mp3"):
                yield os.path.join(root, name)


def plan(path: str | os.PathLike) -> dict:
    """Dry run: return {file: [tags_that_would_be_removed]} for files with junk."""
    report: dict[str, list[str]] = {}
    for p in _audio_files(path):
        audio = File(p, easy=False)
        if audio is None or audio.tags is None:
            continue
        to_del = _junk_for(audio, os.path.splitext(p)[1].lower())
        if to_del:
            report[p] = sorted(set(to_del))
    return report


def apply(path: str | os.PathLike, log=None) -> dict:
    """Remove junk tags in place. Returns a summary dict."""
    log = log or (lambda _m: None)
    removed = collections.Counter()
    touched = kept = skipped = 0
    for p in _audio_files(path):
        ext = os.path.splitext(p)[1].lower()
        audio = File(p, easy=False)
        if audio is None or audio.tags is None:
            skipped += 1
            continue
        to_del = _junk_for(audio, ext)
        if not to_del:
            kept += 1
            continue
        for k in to_del:
            del audio.tags[k]
        try:
            audio.save()
        except Exception as e:  # noqa: BLE001
            log(f"ERROR saving {p}: {e}")
            continue
        touched += 1
        for k in to_del:
            removed[k.upper().split(":")[0]] += 1
        log(f"{os.path.basename(p)}: removed {', '.join(sorted(set(to_del)))}")
    return {
        "touched": touched,
        "kept": kept,
        "skipped": skipped,
        "removed": dict(removed.most_common()),
    }
