"""Prototype labels — one free-text label per (model_id, prototype_index)."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Model, PrototypeLabel
from app.models.schemas import PrototypeLabelInfo, PrototypeLabelUpsert

router = APIRouter(prefix="/api/prototype-labels", tags=["labels"])


def _to_info(row: PrototypeLabel) -> PrototypeLabelInfo:
    return PrototypeLabelInfo.model_validate(row)


@router.get("", response_model=list[PrototypeLabelInfo])
def list_labels(
    model_id: str = Query(...), db: Session = Depends(get_db)
) -> list[PrototypeLabelInfo]:
    rows = (
        db.query(PrototypeLabel)
        .filter(PrototypeLabel.model_id == model_id)
        .order_by(PrototypeLabel.prototype_index.asc())
        .all()
    )
    return [_to_info(r) for r in rows]


@router.post("", response_model=PrototypeLabelInfo)
def upsert_label(
    payload: PrototypeLabelUpsert, db: Session = Depends(get_db)
) -> PrototypeLabelInfo:
    model = db.get(Model, payload.model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found.")
    if payload.prototype_index >= model.n_proto:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"prototype_index {payload.prototype_index} >= n_proto={model.n_proto}.",
        )

    row = (
        db.query(PrototypeLabel)
        .filter(
            PrototypeLabel.model_id == payload.model_id,
            PrototypeLabel.prototype_index == payload.prototype_index,
        )
        .one_or_none()
    )
    now = datetime.utcnow()
    if row is None:
        row = PrototypeLabel(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            model_id=payload.model_id,
            prototype_index=payload.prototype_index,
            label=payload.label,
        )
    else:
        row.label = payload.label
        row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_info(row)


@router.delete("/{label_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_label(label_id: str, db: Session = Depends(get_db)) -> Response:
    row = db.get(PrototypeLabel, label_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found.")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
