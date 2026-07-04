"""
In-memory job store + background execution.

The pipeline is CPU-bound (Whisper) and can take a while, so it's run
in a background thread rather than blocking a request. State lives in
a process-local dict, which is fine for a single-instance deployment.
For multi-instance/production deployments, swap this out for a real
task queue (Celery, RQ, arq) and a shared store (Redis/Postgres) -
the `JobStore` interface below is intentionally small so that's a
drop-in replacement, not a rewrite.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.core.exceptions import MeetingIntelligenceError
from app.core.pipeline import MeetingAnalysis, run_pipeline
from app.api.schemas import JobStatus

logger = logging.getLogger(__name__)

# Tune based on expected concurrent load / CPU cores available for Whisper.
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline-worker")

# How long a completed/failed job's data is kept before eviction.
_JOB_TTL_SECONDS = 60 * 60 * 6  # 6 hours


@dataclass
class Job:
    job_id: str
    status: JobStatus = JobStatus.queued
    result: MeetingAnalysis | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self) -> Job:
        job = Job(job_id=uuid.uuid4().hex[:16])
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)
            job.updated_at = time.time()

    def evict_expired(self) -> None:
        cutoff = time.time() - _JOB_TTL_SECONDS
        with self._lock:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in (JobStatus.completed, JobStatus.failed)
                and job.updated_at < cutoff
            ]
            for job_id in expired:
                del self._jobs[job_id]

    def submit(
        self,
        source: str,
        language: str,
        chunk_minutes: int | None,
        build_index: bool,
    ) -> Job:
        job = self.create()
        _EXECUTOR.submit(
            self._run, job.job_id, source, language, chunk_minutes, build_index
        )
        return job

    def _run(
        self,
        job_id: str,
        source: str,
        language: str,
        chunk_minutes: int | None,
        build_index: bool,
    ) -> None:
        self._update(job_id, status=JobStatus.processing)
        logger.info("Job %s started.", job_id)

        try:
            result = run_pipeline(
                source=source,
                language=language,
                chunk_minutes=chunk_minutes,
                build_index=build_index,
            )
            self._update(job_id, status=JobStatus.completed, result=result)
            logger.info("Job %s completed (meeting_id=%s).", job_id, result.meeting_id)
        except MeetingIntelligenceError as exc:
            logger.warning("Job %s failed: %s", job_id, exc)
            self._update(job_id, status=JobStatus.failed, error=str(exc))
        except Exception as exc:  # noqa: BLE001 - never let a worker thread die silently
            logger.exception("Job %s failed with an unexpected error.", job_id)
            self._update(job_id, status=JobStatus.failed, error=f"Unexpected error: {exc}")


job_store = JobStore()
