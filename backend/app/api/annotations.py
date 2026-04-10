from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Annotation
from app.schemas import AnnotationRequest, AnnotationResponse

router = APIRouter(prefix="/api/v1", tags=["annotations"])


@router.post("/annotations", response_model=AnnotationResponse, status_code=201)
def create_annotation(
    payload: AnnotationRequest, db: Session = Depends(get_db)
) -> AnnotationResponse:
    annotation = Annotation(
        id=uuid4().hex,
        target_id=payload.target_id,
        target_type=payload.target_type,
        note=payload.note,
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return AnnotationResponse(annotation_id=annotation.id)
