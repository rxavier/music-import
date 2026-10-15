# music-import

Web frontend for a music-import pipeline. Scans release folders, shows each
release's *shape* (single CD image vs already-split tracks vs APE/WavPack
image), runs fake-lossless (transcode) diagnostics, cleans non-standard tags,
splits/converts CD images into tagged FLAC tracks, and drives an interactive
`beet import` in the browser.

It is a thin UI over existing tools. The Python modules are ports of the
shell/micro-tools this replaces (`splitrename`, `clean-music-tags`,
`albumcheck`); external binaries are invoked as subprocesses.

## What it does

- **Scan** the download sources and classify each release folder by shape.
- **Diagnose**: run `flaccheck` and roll per-file verdicts up per album
  (TRANSCODE / SUSPECT / CHECK / CLEAN / INCONCLUSIVE).
- **Hi-res**: detect >48 kHz FLACs, estimate the reclaim, and downsample to
  48/24 (staged, originals untouched).
- **Clean tags**: dry-run then strip ripper junk / non-standard tags (mutagen).
- **Split/convert**: FLAC+cue, APE+cue, and WavPack/ISO (~`.wv`) images.
- **Import**: an interactive `beet import` in a browser terminal (xterm.js).

Nothing is ever deleted; the source files are left in place.

## Requirements

External binaries (resolved from `PATH`):

- `ffmpeg`, `flac` (for `metaflac`)
- `shntool` (provides `shnsplit`, `cuetag`, `cuebreakpoints`)
- `wavpack` (`wvunpack`), `p7zip` (`7z`)
- [`flaccheck`](https://github.com/dasunNimantha/flaccheck) — fake-lossless detector
- [`beets`](https://beets.io) — for the import step

Python 3.12+ and [`uv`](https://github.com/astral-sh/uv).

## Run

```sh
uv run music-import
```

Then open http://127.0.0.1:8318/.

## Configuration

All paths and tool locations are environment-overridable; see
`src/musicimport/config.py`. The common ones:

| variable | default | meaning |
| --- | --- | --- |
| `MUSIC_IMPORT_MEDIA` | `/media` | media tree root |
| `MUSIC_IMPORT_HOST` / `MUSIC_IMPORT_PORT` | `127.0.0.1` / `8318` | web bind |
| `MUSIC_IMPORT_TORRENTS` | `<media>/downloads/torrents/complete` | torrent releases (descends into `lidarr/`) |
| `MUSIC_IMPORT_SOULSEEK` | `<media>/downloads/soulseek/complete` | Soulseek releases |
| `MUSIC_IMPORT_MUSIC` | `<media>/music` | beets library |
| `MUSIC_IMPORT_FLACCHECK` / `MUSIC_IMPORT_BEET` | `flaccheck` / `beet` | tool paths |

## Deploy as a systemd user service

A unit template lives in `packaging/music-import.service`. Copy it to
`~/.config/systemd/user/`, adjust the project path if you did not clone to
`~/code/music-import`, drop your settings in
`~/.config/music-import/music-import.env`, then:

```sh
systemctl --user daemon-reload
systemctl --user enable --now music-import
```
