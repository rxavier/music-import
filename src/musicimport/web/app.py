"""FastAPI app: scan/diagnose/split/convert/tag/downsample + beets terminal."""
from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import beets_runner, convert, diagnostics, hires, scan, splitrename, tags
from ..config import MEDIA
from ..jobs import MANAGER

STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="music-import")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

_MEDIA_ROOT = MEDIA.resolve()


def safe_path(raw: str | None) -> Path:
    if not raw:
        raise HTTPException(400, "missing path")
    p = Path(raw).resolve()
    if p != _MEDIA_ROOT and _MEDIA_ROOT not in p.parents:
        raise HTTPException(403, f"path outside media root: {p}")
    return p


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC / "index.html"))


@app.get("/api/releases")
def api_releases() -> list[dict]:
    return scan.releases()


@app.get("/api/release")
def api_release(path: str) -> dict:
    p = safe_path(path)
    if not p.is_dir():
        raise HTTPException(404, "no such release folder")
    return scan.release(p)


@app.post("/api/release/diagnose")
async def api_diagnose(req: Request) -> dict:
    body = await req.json()
    p = safe_path(body.get("path"))
    job = MANAGER.start("diagnose", str(p),
                        lambda log: {"albums": diagnostics.analyze(p, log)})
    return {"job": job.id}


@app.post("/api/release/hires")
async def api_hires(req: Request) -> dict:
    body = await req.json()
    p = safe_path(body.get("path"))
    return {"info": hires.detect(p)}


@app.post("/api/release/tags/dry-run")
async def api_tags_dry(req: Request) -> dict:
    body = await req.json()
    p = safe_path(body.get("path"))
    plan = tags.plan(p)
    return {
        "files": len(plan),
        "total_tags": sum(len(v) for v in plan.values()),
        "plan": {os.path.relpath(k, p): v for k, v in plan.items()},
    }


@app.post("/api/release/tags/clean")
async def api_tags_clean(req: Request) -> dict:
    body = await req.json()
    p = safe_path(body.get("path"))
    job = MANAGER.start("clean-tags", str(p), lambda log: tags.apply(p, log))
    return {"job": job.id}


@app.post("/api/release/split")
async def api_split(req: Request) -> dict:
    body = await req.json()
    p = safe_path(body.get("path"))

    def work(log):
        return {"tracks": [str(t) for t in splitrename.split_release(p, log)]}

    job = MANAGER.start("split", str(p), work)
    return {"job": job.id}


@app.post("/api/release/convert")
async def api_convert(req: Request) -> dict:
    body = await req.json()
    p = safe_path(body.get("path"))
    shape = scan.classify(p)

    def work(log):
        if shape["shape"] == "ape_cue":
            return {"tracks": [str(t) for t in convert.convert_ape(p, log)]}
        if shape["shape"] == "wv_iso":
            return {"out": str(convert.convert_wv(p, log))}
        raise RuntimeError(f"nothing to convert for shape {shape['shape']}")

    job = MANAGER.start("convert", str(p), work)
    return {"job": job.id}


@app.post("/api/release/downsample")
async def api_downsample(req: Request) -> dict:
    body = await req.json()
    p = safe_path(body.get("path"))
    job = MANAGER.start("downsample", str(p),
                        lambda log: {"out": str(hires.downsample(p, log=log))})
    return {"job": job.id}


@app.get("/api/jobs/{jid}")
def api_job(jid: str, since: int = 0) -> dict:
    job = MANAGER.get(jid)
    if job is None:
        raise HTTPException(404, "no such job")
    return job.as_dict(since)


@app.get("/api/jobs/{jid}/stream")
async def api_job_stream(jid: str) -> StreamingResponse:
    if MANAGER.get(jid) is None:
        raise HTTPException(404, "no such job")

    async def gen():
        idx = 0
        while True:
            job = MANAGER.get(jid)
            if job is None:
                break
            lines = job.lines[idx:]
            for line in lines:
                idx += 1
                yield f"data: {json.dumps(line)}\n\n"
            if job.status != "running":
                payload = job.as_dict(len(job.lines))
                yield f"event: done\ndata: {json.dumps(payload)}\n\n"
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.websocket("/ws/beets")
async def ws_beets(ws: WebSocket) -> None:
    await ws.accept()
    try:
        p = safe_path(ws.query_params.get("path"))
    except HTTPException as e:
        await ws.send_text(f"\r\n{e.detail}\r\n")
        await ws.close()
        return
    if not p.is_dir():
        await ws.send_text(f"\r\nnot a folder: {p}\r\n")
        await ws.close()
        return

    master, child = beets_runner.spawn(str(p))
    beets_runner.set_winsize(master, 40, 120)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def reader() -> None:
        while True:
            data = beets_runner.read(master)
            if not data:
                break
            loop.call_soon_threadsafe(queue.put_nowait, data)
        loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=reader, daemon=True).start()

    async def pump_out() -> None:
        while True:
            data = await queue.get()
            if data is None:
                break
            await ws.send_text(data.decode("utf-8", "replace"))

    out_task = asyncio.create_task(pump_out())
    try:
        while True:
            msg = await ws.receive_text()
            try:
                ctl = json.loads(msg)
            except json.JSONDecodeError:
                beets_runner.write(master, msg.encode())
                continue
            if ctl.get("type") == "input":
                beets_runner.write(master, ctl.get("data", "").encode())
            elif ctl.get("type") == "resize":
                beets_runner.set_winsize(master, ctl.get("rows", 40),
                                         ctl.get("cols", 120))
    except WebSocketDisconnect:
        pass
    finally:
        out_task.cancel()
        beets_runner.close(master, child)
