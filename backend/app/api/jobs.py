from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Job
from app.schemas import JobOut, JobStatusResponse, ReorderRequest, ReorderResponse

router = APIRouter(prefix="/api/v1", tags=["jobs"])


_PROGRESS_BY_STATUS = {"Queued": 0, "Processing": 50, "Done": 100, "Error": 100}


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db)) -> list[JobOut]:
    jobs = (
        db.query(Job)
        .order_by(Job.priority.asc(), Job.created_at.asc())
        .all()
    )
    return [JobOut.model_validate(j) for j in jobs]


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=_PROGRESS_BY_STATUS.get(job.status, 0),
    )


@router.put("/jobs/reorder", response_model=ReorderResponse)
def reorder_jobs(payload: ReorderRequest, db: Session = Depends(get_db)) -> ReorderResponse:
    if not payload.ordered_job_ids:
        raise HTTPException(status_code=400, detail="ordered_job_ids must not be empty")

    # Validate all referenced jobs are Queued before mutating anything.
    jobs = db.query(Job).filter(Job.id.in_(payload.ordered_job_ids)).all()
    by_id = {j.id: j for j in jobs}

    missing = [jid for jid in payload.ordered_job_ids if jid not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown job ids: {missing}")

    not_queued = [j.id for j in jobs if j.status != "Queued"]
    if not_queued:
        # 409: cannot reorder a job that is already Processing/Done/Error.
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reorder jobs not in Queued state: {not_queued}",
        )

    # Listed jobs go first (0..N-1) in the requested order.
    for new_priority, jid in enumerate(payload.ordered_job_ids):
        by_id[jid].priority = new_priority

    # Unlisted Queued jobs follow (N..) preserving their original relative FIFO order.
    listed_ids = set(payload.ordered_job_ids)
    unlisted = (
        db.query(Job)
        .filter(Job.status == "Queued", Job.id.notin_(listed_ids))
        .order_by(Job.priority.asc(), Job.created_at.asc())
        .all()
    )
    for i, j in enumerate(unlisted):
        j.priority = len(payload.ordered_job_ids) + i
    db.commit()

    return ReorderResponse(ordered_job_ids=payload.ordered_job_ids)
