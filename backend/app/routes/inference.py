"""Inference REST endpoints (per plan §6e).

Single + batch dispatch, cache lookup, rerun, and the notes CRUD that
attaches free-text observations to a completed inference.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Inference, InferenceBatch, InferenceNote, Model, PrototypeLabel
from app.models.schemas import (
    ExamplePatchGroup,
    ExamplePatchesResponse,
    InferenceBatchInfo,
    InferenceCreateRequest,
    InferenceCreateResponse,
    InferenceDispatchEntry,
    InferenceInfo,
    InferenceLookupResponse,
    InferenceNoteCreate,
    InferenceNoteInfo,
    InferenceNotePatch,
    InferenceRerunResponse,
)
from app.services import inference as inference_service
from app.services.fs import resolve_within_roots
from app.services.worker import enqueue_job

router = APIRouter(prefix="/api", tags=["inferences"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_info(row: Inference) -> InferenceInfo:
    return InferenceInfo.model_validate(row)


def _validate_wsi_path(raw: str) -> tuple[Path | None, str | None]:
    """Reject anything outside TRIDENT_ALLOWED_ROOTS. Returns (path|None, error|None)."""
    try:
        resolved = resolve_within_roots(raw)
    except HTTPException as exc:
        return None, str(exc.detail)
    if not resolved.is_file():
        return None, f"WSI file does not exist: {resolved}"
    return resolved, None


def _create_inference_row(
    db: Session,
    *,
    model: Model,
    wsi_path: Path,
    batch_id: str | None,
) -> Inference:
    inference_id = str(uuid.uuid4())
    stat = wsi_path.stat()
    output_dir = inference_service.inference_output_dir(model.id, inference_id)
    row = Inference(
        id=inference_id,
        created_at=datetime.utcnow(),
        model_id=model.id,
        batch_id=batch_id,
        wsi_path=str(wsi_path),
        wsi_filename=wsi_path.name,
        wsi_mtime=stat.st_mtime,
        wsi_size=stat.st_size,
        wsi_hash="",  # handler will compute and store
        output_dir=str(output_dir),
        status="queued",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# POST /api/inferences  (single + batch dispatch)
# ---------------------------------------------------------------------------


@router.post("/inferences", response_model=InferenceCreateResponse)
def create_inferences(
    payload: InferenceCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> InferenceCreateResponse:
    model = db.get(Model, payload.model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {payload.model_id!r} not found.",
        )

    # First pass: validate every path. We collect entries even for rejected
    # paths so the client can show per-row errors.
    validated: list[tuple[str, Path | None, str | None]] = []
    for raw in payload.wsi_paths:
        resolved, err = _validate_wsi_path(raw)
        validated.append((raw, resolved, err))

    rejected = sum(1 for _, p, _ in validated if p is None)
    if rejected == len(validated):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All wsi_paths failed validation.",
        )

    valid_count = len(validated) - rejected
    batch_id: str | None = None
    if valid_count > 1:
        batch_id = str(uuid.uuid4())
        db.add(
            InferenceBatch(
                id=batch_id,
                created_at=datetime.utcnow(),
                model_id=model.id,
                user_label=payload.batch_label,
                total_count=valid_count,
            )
        )
        db.commit()

    entries: list[InferenceDispatchEntry] = []
    enqueued_any = False

    for raw, resolved, err in validated:
        if resolved is None:
            entries.append(
                InferenceDispatchEntry(
                    wsi_path=raw,
                    status="rejected",
                    cached=False,
                    message=err,
                )
            )
            continue

        # Cache hit short-circuit (unless caller explicitly forces rerun).
        if not payload.rerun:
            cached = inference_service.lookup_cached_inference(db, model.id, resolved)
            if cached is not None:
                entries.append(
                    InferenceDispatchEntry(
                        wsi_path=str(resolved),
                        status=cached.status,
                        id=cached.id,
                        cached=True,
                        message="cache hit",
                    )
                )
                continue

        row = _create_inference_row(db, model=model, wsi_path=resolved, batch_id=batch_id)
        job = enqueue_job(
            db, job_type="inference", ref_table="inferences", ref_id=row.id
        )
        enqueued_any = True
        entries.append(
            InferenceDispatchEntry(
                wsi_path=str(resolved),
                status="queued",
                id=row.id,
                cached=False,
                message=f"queued as job {job.id}",
            )
        )

    # 207 if some paths were rejected but others succeeded.
    if rejected > 0 and (enqueued_any or any(e.cached for e in entries)):
        response.status_code = status.HTTP_207_MULTI_STATUS

    return InferenceCreateResponse(batch_id=batch_id, inferences=entries)


# ---------------------------------------------------------------------------
# Cache lookup (without creating)
# ---------------------------------------------------------------------------


@router.get("/inferences/lookup", response_model=InferenceLookupResponse)
def lookup(
    model_id: str = Query(...),
    wsi_path: str = Query(...),
    db: Session = Depends(get_db),
) -> InferenceLookupResponse:
    resolved, err = _validate_wsi_path(wsi_path)
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    cached = inference_service.lookup_cached_inference(db, model_id, resolved)
    if cached is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No cached inference."
        )
    return InferenceLookupResponse.model_validate(cached)


# ---------------------------------------------------------------------------
# List + detail
# ---------------------------------------------------------------------------


@router.get("/inferences", response_model=list[InferenceInfo])
def list_inferences(
    model_id: str | None = Query(None),
    batch_id: str | None = Query(None),
    status_: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[InferenceInfo]:
    q = db.query(Inference).order_by(Inference.created_at.desc())
    if model_id:
        q = q.filter(Inference.model_id == model_id)
    if batch_id:
        q = q.filter(Inference.batch_id == batch_id)
    if status_:
        q = q.filter(Inference.status == status_)
    return [_to_info(r) for r in q.limit(limit).all()]


@router.get("/inferences/{inference_id}", response_model=InferenceInfo)
def get_inference(inference_id: str, db: Session = Depends(get_db)) -> InferenceInfo:
    row = db.get(Inference, inference_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inference not found."
        )
    return _to_info(row)


@router.get(
    "/inferences/{inference_id}/example-patches",
    response_model=ExamplePatchesResponse,
)
def list_example_patches(
    inference_id: str, db: Session = Depends(get_db)
) -> ExamplePatchesResponse:
    """List the patch image files written to inference.example_patches_dir.

    Returns one group per prototype with absolute URLs that route through
    /api/viz/{path}. The renderer (render_example_patches) lays out the
    directory as `prototype_{NN}/patch_{NN}.png` — we walk that structure
    and return the file URLs in stable order.
    """
    inference = db.get(Inference, inference_id)
    if inference is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inference not found."
        )
    if not inference.example_patches_dir:
        return ExamplePatchesResponse(
            inference_id=inference.id, base_dir="", groups=[]
        )
    base = Path(inference.example_patches_dir)
    if not base.is_dir():
        # Path is recorded on the row but the directory isn't on disk —
        # could be a seed-only row (paths are fake) or an old run whose
        # files got cleaned. Return empty groups, never 500.
        return ExamplePatchesResponse(
            inference_id=inference.id, base_dir=str(base), groups=[]
        )

    # Optional: look up prototype labels so the UI can show them inline.
    labels: dict[int, str] = {
        row.prototype_index: row.label
        for row in (
            db.query(PrototypeLabel)
            .filter(PrototypeLabel.model_id == inference.model_id)
            .all()
        )
    }

    groups: list[ExamplePatchGroup] = []
    for sub in sorted(base.iterdir()):
        if not sub.is_dir() or not sub.name.startswith("prototype_"):
            continue
        try:
            proto_idx = int(sub.name.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        urls = [
            f"/api/viz/{patch.resolve()}"
            for patch in sorted(sub.iterdir())
            if patch.is_file() and patch.suffix.lower() in {".png", ".jpg", ".jpeg"}
        ]
        if not urls:
            continue
        groups.append(
            ExamplePatchGroup(
                prototype_index=proto_idx,
                label=labels.get(proto_idx),
                urls=urls,
            )
        )

    return ExamplePatchesResponse(
        inference_id=inference.id, base_dir=str(base), groups=groups
    )


# ---------------------------------------------------------------------------
# Rerun
# ---------------------------------------------------------------------------


@router.post("/inferences/{inference_id}/rerun", response_model=InferenceRerunResponse)
def rerun_inference(
    inference_id: str, db: Session = Depends(get_db)
) -> InferenceRerunResponse:
    old = db.get(Inference, inference_id)
    if old is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inference not found."
        )
    model = db.get(Model, old.model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Inference references a model that no longer exists.",
        )
    wsi_path = Path(old.wsi_path)
    if not wsi_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot rerun: WSI file no longer exists at {wsi_path}.",
        )

    # Invalidate the cached row (and its notes) before creating the fresh one.
    db.query(InferenceNote).filter(InferenceNote.inference_id == old.id).delete(
        synchronize_session=False
    )
    db.delete(old)
    db.commit()

    fresh = _create_inference_row(db, model=model, wsi_path=wsi_path, batch_id=None)
    job = enqueue_job(
        db, job_type="inference", ref_table="inferences", ref_id=fresh.id
    )
    return InferenceRerunResponse(new_inference_id=fresh.id, job_id=job.id)


# ---------------------------------------------------------------------------
# Inference batches
# ---------------------------------------------------------------------------


@router.get("/inference-batches/{batch_id}", response_model=InferenceBatchInfo)
def get_batch(batch_id: str, db: Session = Depends(get_db)) -> InferenceBatchInfo:
    row = db.get(InferenceBatch, batch_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found."
        )
    return InferenceBatchInfo.model_validate(row)


# ---------------------------------------------------------------------------
# Inference notes
# ---------------------------------------------------------------------------


@router.get("/inference-notes", response_model=list[InferenceNoteInfo])
def list_notes(
    inference_id: str = Query(...), db: Session = Depends(get_db)
) -> list[InferenceNoteInfo]:
    rows = (
        db.query(InferenceNote)
        .filter(InferenceNote.inference_id == inference_id)
        .order_by(InferenceNote.created_at.desc())
        .all()
    )
    return [InferenceNoteInfo.model_validate(r) for r in rows]


@router.post("/inference-notes", response_model=InferenceNoteInfo)
def create_note(
    payload: InferenceNoteCreate, db: Session = Depends(get_db)
) -> InferenceNoteInfo:
    inference = db.get(Inference, payload.inference_id)
    if inference is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inference not found."
        )
    now = datetime.utcnow()
    row = InferenceNote(
        id=str(uuid.uuid4()),
        created_at=now,
        updated_at=now,
        inference_id=payload.inference_id,
        body=payload.body,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return InferenceNoteInfo.model_validate(row)


@router.patch("/inference-notes/{note_id}", response_model=InferenceNoteInfo)
def update_note(
    note_id: str, payload: InferenceNotePatch, db: Session = Depends(get_db)
) -> InferenceNoteInfo:
    row = db.get(InferenceNote, note_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found."
        )
    row.body = payload.body
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return InferenceNoteInfo.model_validate(row)


@router.delete(
    "/inference-notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_note(note_id: str, db: Session = Depends(get_db)) -> Response:
    row = db.get(InferenceNote, note_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found."
        )
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
