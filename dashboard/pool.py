"""
Pool 3 worker nền — lấy job QUEUED rồi chạy hết pipeline.
ponytail: thread in-process + claim lock (SQLite). Restart server = restart worker.
"""

from __future__ import annotations

import logging
import threading
import time

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)

_started = False
_start_lock = threading.Lock()
_claim_lock = threading.Lock()
_busy = 0
_busy_lock = threading.Lock()


def worker_count() -> int:
    return int(getattr(settings, "WORKER_COUNT", 3))


def worker_stats() -> dict:
    n = worker_count()
    with _busy_lock:
        busy = _busy
    return {
        "total": n,
        "busy": busy,
        "idle": max(0, n - busy),
        "online": n if _started else 0,
    }


def _set_busy(delta: int):
    global _busy
    with _busy_lock:
        _busy = max(0, _busy + delta)


def claim_job(worker_name: str):
    """Claim tuần tự — tránh SQLite database is locked."""
    from .models import GenerationJob

    with _claim_lock:
        close_old_connections()
        job = (
            GenerationJob.objects.filter(status=GenerationJob.Status.QUEUED)
            .order_by("created_at")
            .first()
        )
        if not job:
            return None
        n = GenerationJob.objects.filter(
            pk=job.pk, status=GenerationJob.Status.QUEUED
        ).update(
            status=GenerationJob.Status.WORKER,
            message=f"{worker_name} nhận job…",
            updated_at=timezone.now(),
        )
        return job.pk if n else None


def process_job(job_id: int, worker_name: str):
    """Chạy pipeline đến DONE / NEED_RERUN / FAILED."""
    from . import views
    from .models import GenerationJob

    close_old_connections()
    job = GenerationJob.objects.filter(pk=job_id).first()
    if not job:
        return

    for _ in range(12):
        close_old_connections()
        job.refresh_from_db()
        if job.status in (
            GenerationJob.Status.DONE,
            GenerationJob.Status.NEED_RERUN,
            GenerationJob.Status.FAILED,
        ):
            break
        job.message = f"{worker_name}: {job.get_status_display()}"
        job.save(update_fields=["message", "updated_at"])
        views._advance_job(job)
        time.sleep(0.2)


def _loop(worker_name: str):
    while True:
        try:
            job_id = claim_job(worker_name)
            if job_id is None:
                time.sleep(0.8)
                continue
            _set_busy(1)
            try:
                logger.info("%s processing job #%s", worker_name, job_id)
                process_job(job_id, worker_name)
            finally:
                _set_busy(-1)
        except Exception:
            logger.exception("%s error; continue", worker_name)
            close_old_connections()
            time.sleep(1.5)


def start_workers():
    global _started
    with _start_lock:
        if _started:
            return
        n = worker_count()
        for i in range(1, n + 1):
            t = threading.Thread(
                target=_loop,
                args=(f"Worker-{i}",),
                name=f"ugt-worker-{i}",
                daemon=True,
            )
            t.start()
            logger.info("Started %s", t.name)
        _started = True
