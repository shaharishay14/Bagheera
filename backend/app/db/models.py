"""SQLAlchemy ORM models.

NOTE: schema is created via `Base.metadata.create_all()` (no migrations).
After making column changes, delete `bagheera.db` to recreate.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class TridentRun(Base):
    __tablename__ = "trident_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(64), nullable=False)
    wsi_dir: Mapped[str] = mapped_column(String, nullable=False)
    patch_encoder: Mapped[str] = mapped_column(String(32), nullable=False)
    mag: Mapped[int] = mapped_column(Integer, nullable=False)
    patch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    command: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    stdout: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stderr: Mapped[str] = mapped_column(Text, default="", nullable=False)
    output_dir: Mapped[str] = mapped_column(String, nullable=False)
    return_code: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Split(Base):
    """A K-fold split on disk. One row per split_name."""

    __tablename__ = "splits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    split_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    abs_path: Mapped[str] = mapped_column(String, nullable=False)
    source_csv: Mapped[str] = mapped_column(String, nullable=False)
    k: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    # JSON-encoded list[{"train": N, "val": N, "test": N}] of length K
    per_fold_counts: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class ModelGroup(Base):
    """One PANTHER form submission. Owns K Model rows (one per fold)."""

    __tablename__ = "model_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # == group_id (uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trident_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trident_runs.id"), nullable=True
    )
    k: Mapped[int] = mapped_column(Integer, nullable=False)
    split_id: Mapped[str] = mapped_column(String(36), ForeignKey("splits.id"), nullable=False)


class Model(Base):
    """A trained PANTHER model — one per fold."""

    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("group_id", "fold_index", name="uq_models_group_fold"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Naming
    base_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")

    # Grouping (K models per form submission)
    group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    fold_index: Mapped[int] = mapped_column(Integer, nullable=False)
    fold_k: Mapped[int] = mapped_column(Integer, nullable=False)  # total K

    # Inputs
    dataset_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    features_dir: Mapped[str] = mapped_column(String, nullable=False)
    trident_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trident_runs.id"), nullable=True
    )
    split_id: Mapped[str] = mapped_column(String(36), ForeignKey("splits.id"), nullable=False)
    split_name: Mapped[str] = mapped_column(String(128), nullable=False)
    split_dir_abs: Mapped[str] = mapped_column(String, nullable=False, default="")

    # PANTHER hyperparameters
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    in_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    n_proto_patches: Mapped[int] = mapped_column(Integer, nullable=False)
    n_proto: Mapped[int] = mapped_column(Integer, nullable=False)
    n_init: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    num_workers: Mapped[int] = mapped_column(Integer, nullable=False)

    # Outcome
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    prototypes_dir: Mapped[str] = mapped_column(String, nullable=False, default="")
    # JSON-encoded list[str] of basenames of .pkl / .pt files under prototypes_dir
    prototype_files: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # User flags
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Pre-rendered visualization artifacts
    viz_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # JSON-encoded list of slide IDs used for the per-fold preview heatmaps
    preview_slide_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON-encoded list of absolute paths to those preview heatmaps
    preview_heatmap_paths: Mapped[str | None] = mapped_column(Text, nullable=True)
    topk_grid_path: Mapped[str | None] = mapped_column(String, nullable=True)
    topk_per_proto: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    umap_path: Mapped[str | None] = mapped_column(String, nullable=True)


class PantherRun(Base):
    """Per-fold execution log of the PANTHER subprocess. One row per fold attempt."""

    __tablename__ = "panther_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    fold_index: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[str] = mapped_column(String(36), ForeignKey("models.id"), nullable=False)

    dataset_name: Mapped[str] = mapped_column(String(64), nullable=False)
    features_dir: Mapped[str] = mapped_column(String, nullable=False)
    split_name: Mapped[str] = mapped_column(String(128), nullable=False)

    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    in_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    n_proto_patches: Mapped[int] = mapped_column(Integer, nullable=False)
    n_proto: Mapped[int] = mapped_column(Integer, nullable=False)
    n_init: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    num_workers: Mapped[int] = mapped_column(Integer, nullable=False)

    command: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    stdout: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stderr: Mapped[str] = mapped_column(Text, default="", nullable=False)
    return_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PrototypeLabel(Base):
    """Free-text label attached to one prototype of one fold model."""

    __tablename__ = "prototype_labels"
    __table_args__ = (
        UniqueConstraint("model_id", "prototype_index", name="uq_proto_label_model_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    model_id: Mapped[str] = mapped_column(String(36), ForeignKey("models.id"), nullable=False)
    prototype_index: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class ModelNote(Base):
    """Free-text note about a fold model."""

    __tablename__ = "model_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("models.id"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)


class InferenceBatch(Base):
    """Groups multiple inferences submitted together."""

    __tablename__ = "inference_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("models.id"), nullable=False, index=True
    )
    user_label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)


class Inference(Base):
    """One (fold model, WSI) inference run. Cached by (model_id, wsi_hash)."""

    __tablename__ = "inferences"
    __table_args__ = (
        UniqueConstraint("model_id", "wsi_hash", name="uq_inference_model_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("models.id"), nullable=False, index=True
    )
    batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("inference_batches.id"), nullable=True, index=True
    )

    wsi_path: Mapped[str] = mapped_column(String, nullable=False)
    wsi_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    wsi_mtime: Mapped[float] = mapped_column(Float, nullable=False)
    wsi_size: Mapped[int] = mapped_column(Integer, nullable=False)
    wsi_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    output_dir: Mapped[str] = mapped_column(String, nullable=False)
    features_h5_path: Mapped[str | None] = mapped_column(String, nullable=True)
    heatmap_path: Mapped[str | None] = mapped_column(String, nullable=True)
    mixture_plot_path: Mapped[str | None] = mapped_column(String, nullable=True)
    example_patches_dir: Mapped[str | None] = mapped_column(String, nullable=True)
    tsne_path: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class InferenceNote(Base):
    """Free-text note attached to an inference."""

    __tablename__ = "inference_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    inference_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inferences.id"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)


class Job(Base):
    """Async job tracked by the background worker thread."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    job_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # ref_table + ref_id identify the row this job operates on
    ref_table: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_id: Mapped[str] = mapped_column(String(36), nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_path: Mapped[str | None] = mapped_column(String, nullable=True)
