"""Free-text notes attached to fold models."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Model, ModelNote
from app.models.schemas import ModelNoteCreate, ModelNoteInfo, ModelNotePatch

router = APIRouter(prefix="/api/model-notes", tags=["notes"])


def _to_info(row: ModelNote) -> ModelNoteInfo:
    return ModelNoteInfo.model_validate(row)


@router.get("", response_model=list[ModelNoteInfo])
def list_notes(
    model_id: str = Query(...), db: Session = Depends(get_db)
) -> list[ModelNoteInfo]:
    rows = (
        db.query(ModelNote)
        .filter(ModelNote.model_id == model_id)
        .order_by(ModelNote.created_at.desc())
        .all()
    )
    return [_to_info(r) for r in rows]


@router.post("", response_model=ModelNoteInfo)
def create_note(
    payload: ModelNoteCreate, db: Session = Depends(get_db)
) -> ModelNoteInfo:
    model = db.get(Model, payload.model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found.")
    now = datetime.utcnow()
    row = ModelNote(
        id=str(uuid.uuid4()),
        created_at=now,
        updated_at=now,
        model_id=payload.model_id,
        body=payload.body,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_info(row)


@router.patch("/{note_id}", response_model=ModelNoteInfo)
def update_note(
    note_id: str, payload: ModelNotePatch, db: Session = Depends(get_db)
) -> ModelNoteInfo:
    row = db.get(ModelNote, note_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found.")
    row.body = payload.body
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_info(row)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_note(note_id: str, db: Session = Depends(get_db)) -> Response:
    row = db.get(ModelNote, note_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found.")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
