"""In-memory job registry: runs pipeline steps in a thread and buffers their
log output so the browser can stream it over SSE.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Job:
    id: str
    kind: str
    target: str
    status: str = "running"  # running | done | error
    lines: list[str] = field(default_factory=list)
    result: dict | None = None
    ok: bool = False
    error: str | None = None
    started: float = field(default_factory=time.time)
    finished: float | None = None

    def as_dict(self, since: int = 0) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "target": self.target,
            "status": self.status,
            "ok": self.ok,
            "error": self.error,
            "lines": self.lines[since:],
            "n_lines": len(self.lines),
            "result": self.result,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, jid: str) -> Job | None:
        return self._jobs.get(jid)

    def log(self, job: Job, msg: str) -> None:
        with self._lock:
            job.lines.append(msg)

    def start(self, kind: str, target: str,
              fn: Callable[[Callable[[str], None]], dict | None]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, target=target)
        with self._lock:
            self._jobs[job.id] = job

        def worker() -> None:
            log = lambda m: self.log(job, m)  # noqa: E731
            try:
                result = fn(log)
                with self._lock:
                    job.result = result if isinstance(result, dict) else None
                    job.ok = True
                    job.status = "done"
            except Exception as e:  # noqa: BLE001
                self.log(job, f"ERROR: {e}")
                with self._lock:
                    job.error = str(e)
                    job.ok = False
                    job.status = "error"
            finally:
                with self._lock:
                    job.finished = time.time()

        threading.Thread(target=worker, daemon=True).start()
        return job


MANAGER = JobManager()
