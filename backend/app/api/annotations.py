from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Annotation
from app.schemas import AnnotationOut, AnnotationRequest, AnnotationResponse

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


@router.get("/annotations", response_model=list[AnnotationOut])
def list_annotations(
    target_id: str | None = None,
    target_type: str | None = None,
    db: Session = Depends(get_db),
) -> list[AnnotationOut]:
    q = db.query(Annotation)
    if target_id:
        q = q.filter(Annotation.target_id == target_id)
    if target_type:
        q = q.filter(Annotation.target_type == target_type)
    rows = q.order_by(Annotation.created_at.desc()).all()
    return [
        AnnotationOut(
            annotation_id=r.id,
            target_id=r.target_id,
            target_type=r.target_type,
            note=r.note,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.delete("/annotations/{annotation_id}", status_code=204)
def delete_annotation(annotation_id: str, db: Session = Depends(get_db)) -> None:
    row = db.get(Annotation, annotation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    db.delete(row)
    db.commit()
