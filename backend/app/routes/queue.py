"""Queue page endpoints: the structured queue view + manual reordering.

The shared queue is the `jobs` table. This router gives the Queue page a single
read endpoint plus an atomic reorder; cancel + re-run live on /api/jobs.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Inference, Job, Model, ModelGroup
from app.models.schemas import JobView, QueueReorderRequest, QueueResponse

router = APIRouter(prefix="/api/queue", tags=["queue"])

RECENT_LIMIT = 20


def _title_subtitle(db: Session, job: Job) -> tuple[str, str | None]:
    """Resolve a human label for a job by looking up the row it operates on."""
    if job.job_type == "panther_train":
        group = db.get(ModelGroup, job.ref_id)
        if group is not None:
            return (
                f"PANTHER training — {group.display_name}",
                f"{group.k} folds · {group.dataset_name}",
            )
        return ("PANTHER training", None)
    if job.job_type == "post_train_viz":
        model = db.get(Model, job.ref_id)
        if model is not None:
            return (
                f"Visualization — {model.display_name or model.model_name}",
                f"fold {model.fold_index + 1} of {model.fold_k}",
            )
        return ("Visualization", None)
    if job.job_type == "inference":
        inference = db.get(Inference, job.ref_id)
        if inference is not None:
            return (f"Inference — {inference.wsi_filename}", None)
        return ("Inference", None)
    if job.job_type == "render_slide":
        slide_id = None
        if job.params:
            try:
                slide_id = json.loads(job.params).get("slide_id")
            except (json.JSONDecodeError, AttributeError):
                slide_id = None
        model = db.get(Model, job.ref_id)
        name = (model.display_name or model.model_name) if model is not None else None
        subtitle = " · ".join(p for p in (name, slide_id) if p) or None
        return ("Render slide viz", subtitle)
    return (job.job_type, None)


def _job_view(db: Session, job: Job) -> JobView:
    title, subtitle = _title_subtitle(db, job)
    return JobView(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        ref_table=job.ref_table,
        ref_id=job.ref_id,
        queue_position=job.queue_position,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_message=job.error_message,
        title=title,
        subtitle=subtitle,
    )


def _build_queue(db: Session) -> QueueResponse:
    running = (
        db.query(Job)
        .filter(Job.status == "running")
        .order_by(Job.started_at.asc())
        .first()
    )
    waiting = (
        db.query(Job)
        .filter(Job.status == "queued")
        .order_by(Job.queue_position.asc(), Job.created_at.asc())
        .all()
    )
    recent = (
        db.query(Job)
        .filter(Job.status.in_(["succeeded", "failed", "canceled"]))
        .order_by(Job.finished_at.desc(), Job.created_at.desc())
        .limit(RECENT_LIMIT)
        .all()
    )
    return QueueResponse(
        running=_job_view(db, running) if running is not None else None,
        waiting=[_job_view(db, j) for j in waiting],
        recent=[_job_view(db, j) for j in recent],
    )


@router.get("", response_model=QueueResponse)
def get_queue(db: Session = Depends(get_db)) -> QueueResponse:
    return _build_queue(db)


@router.post("/reorder", response_model=QueueResponse)
def reorder_queue(
    payload: QueueReorderRequest, db: Session = Depends(get_db)
) -> QueueResponse:
    """Atomically rewrite queue_position from the client's desired order.

    Only still-queued jobs are repositioned; ids that have since started or been
    canceled are ignored. Queued jobs the client didn't mention keep their
    relative order and go after the listed ones.
    """
    queued = {j.id: j for j in db.query(Job).filter(Job.status == "queued").all()}

    pos = 1
    seen: set[str] = set()
    for jid in payload.ordered_job_ids:
        job = queued.get(jid)
        if job is None or jid in seen:
            continue
        job.queue_position = pos
        db.add(job)
        seen.add(jid)
        pos += 1

    leftovers = [j for j in queued.values() if j.id not in seen]
    leftovers.sort(key=lambda j: (j.queue_position or 0, j.created_at))
    for job in leftovers:
        job.queue_position = pos
        db.add(job)
        pos += 1

    db.commit()
    return _build_queue(db)
