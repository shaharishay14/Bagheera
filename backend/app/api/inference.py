from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Job
from app.schemas import InferenceRequest, InferenceResponse

router = APIRouter(prefix="/api/v1", tags=["inference"])


@router.post("/inference", response_model=InferenceResponse, status_code=201)
def submit_inference(payload: InferenceRequest, db: Session = Depends(get_db)) -> InferenceResponse:
    # Append-to-tail FIFO: priority = (max existing priority) + 1.
    # created_at is the secondary order, so two jobs at the same priority still resolve.
    max_priority = db.query(Job.priority).order_by(Job.priority.desc()).limit(1).scalar()
    next_priority = (max_priority + 1) if max_priority is not None else 0

    job = Job(
        id=uuid4().hex,
        dataset_id=payload.dataset_id,
        num_clusters=payload.num_clusters,
        status="Queued",
        priority=next_priority,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return InferenceResponse(job_id=job.id, status="Queued")
