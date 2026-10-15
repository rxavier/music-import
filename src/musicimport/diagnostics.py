"""Fake-lossless (transcode) diagnostics.

Port of the ``albumcheck`` roll-up layer: run ``flaccheck`` once over a release
(JSON), group per-file verdicts by album folder, and apply the whole-album
vote. Advisory only — this never moves or deletes anything.
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
from collections import Counter, defaultdict

from . import proc
from .config import FLACCHECK, FLACCHECK_MODE, FLACCHECK_WORKERS, LOSSLESS_EXT
from .proc import Log

STRONG = {"TRANSCODED"}
WEAK = {"SUSPICIOUS"}
UNKNOWN = {"INCONCLUSIVE"}
SEVERITY = ["TRANSCODE", "SUSPECT", "CHECK", "INCONCLUSIVE", "CLEAN"]


def scan(path: str | os.PathLike, log: Log | None = None,
         mode: str | None = None, workers: int | None = None) -> dict:
    """Run flaccheck over ``path`` and return its parsed JSON payload."""
    log = log or (lambda _m: None)
    cmd = [
        FLACCHECK, "scan", str(path),
        "--format", "json", "--quiet",
        "--mode", mode or FLACCHECK_MODE,
        "--workers", str(workers or FLACCHECK_WORKERS),
    ]
    log("$ " + " ".join(cmd))
    out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        return json.loads(out.stdout.decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError:
        log("flaccheck produced no usable JSON")
        return {}


def _cutoff(rec: dict):
    for ev in rec.get("evidence") or []:
        if ev.get("signal") == "cutoff_hz":
            return ev.get("value")
    return None


def _roll_up(records: list[dict]) -> dict:
    verdicts = Counter(r.get("transcode_verdict") for r in records)
    n = len(records)
    n_t = sum(verdicts.get(v, 0) for v in STRONG)
    n_w = sum(verdicts.get(v, 0) for v in WEAK)
    n_u = sum(verdicts.get(v, 0) for v in UNKNOWN)
    n_g = verdicts.get("GENUINE", 0)

    if n and n_t / n >= 0.5:
        status = "TRANSCODE"
    elif n and (n_t + n_w) / n >= 0.5:
        status = "SUSPECT"
    elif n_t + n_w >= 1:
        status = "CHECK"
    elif n and n_u / n >= 0.5:
        status = "INCONCLUSIVE"
    else:
        status = "CLEAN"

    cutoffs = [c for c in (_cutoff(r) for r in records) if c]
    rates = [r.get("sample_rate") for r in records if r.get("sample_rate")]
    codecs = Counter(r.get("codec_guess") for r in records if r.get("codec_guess"))
    confs = [r.get("confidence") for r in records
             if isinstance(r.get("confidence"), (int, float))]
    return {
        "status": status,
        "files": n,
        "genuine": n_g,
        "suspicious": n_w,
        "transcoded": n_t,
        "inconclusive": n_u,
        "flagged": n_t + n_w,
        "cutoff_hz": round(statistics.median(cutoffs)) if cutoffs else None,
        "sample_rate": Counter(rates).most_common(1)[0][0] if rates else None,
        "codec_guess": codecs.most_common(1)[0][0] if codecs else None,
        "mean_confidence": round(statistics.mean(confs), 3) if confs else None,
    }


def analyze(path: str | os.PathLike, log: Log | None = None,
            mode: str | None = None, workers: int | None = None) -> list[dict]:
    """Return one rolled-up record per album folder under ``path``."""
    data = scan(path, log, mode, workers)
    results = [
        r for r in data.get("results", [])
        if os.path.splitext(r.get("path", ""))[1].lower() in LOSSLESS_EXT
    ]
    albums: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        albums[os.path.dirname(r.get("path", ""))].append(r)

    out = []
    for folder, recs in albums.items():
        info = _roll_up(recs)
        info["folder"] = folder
        info["tracks"] = [
            {
                "file": os.path.basename(r.get("path", "")),
                "verdict": r.get("transcode_verdict"),
                "confidence": r.get("confidence"),
            }
            for r in sorted(recs, key=lambda x: x.get("path", ""))
        ]
        out.append(info)
    out.sort(key=lambda a: (SEVERITY.index(a["status"]), -a["flagged"], a["folder"]))
    return out
