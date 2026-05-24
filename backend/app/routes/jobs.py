"""Async job inspection endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Job
from app.models.schemas import JobDetail, JobInfo
from app.services.worker import tail_log

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobInfo])
def list_jobs(
    status_: str | None = Query(None, alias="status"),
    ref_table: str | None = Query(None),
    ref_id: str | None = Query(None),
    job_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[JobInfo]:
    q = db.query(Job).order_by(Job.created_at.desc())
    if status_:
        q = q.filter(Job.status == status_)
    if ref_table:
        q = q.filter(Job.ref_table == ref_table)
    if ref_id:
        q = q.filter(Job.ref_id == ref_id)
    if job_type:
        q = q.filter(Job.job_type == job_type)
    return [JobInfo.model_validate(row) for row in q.limit(limit).all()]


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobDetail:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    base = JobInfo.model_validate(job).model_dump()
    return JobDetail(**base, log_tail=tail_log(job))


@router.post("/{job_id}/retry", response_model=JobInfo)
def retry_job(job_id: str, db: Session = Depends(get_db)) -> JobInfo:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if job.status not in {"failed", "succeeded"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot retry a job in status {job.status!r}; only failed/succeeded.",
        )
    job.status = "queued"
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    # Touch created_at so the retry picks up after currently-queued jobs.
    job.created_at = datetime.utcnow()
    db.add(job)
    db.commit()
    db.refresh(job)
    return JobInfo.model_validate(job)
