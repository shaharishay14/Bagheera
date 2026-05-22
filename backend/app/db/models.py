"""SQLAlchemy ORM models.

NOTE: schema is created via `Base.metadata.create_all()` (no migrations).
After making column changes, delete `bagheera.db` to recreate.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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


class Model(Base):
    """A trained PANTHER model — one per fold."""

    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("group_id", "fold_index", name="uq_models_group_fold"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Naming
    base_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)

    # Grouping (K models per form submission)
    group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    fold_index: Mapped[int] = mapped_column(Integer, nullable=False)
    fold_k: Mapped[int] = mapped_column(Integer, nullable=False)  # total K

    # Inputs
    dataset_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    features_dir: Mapped[str] = mapped_column(String, nullable=False)
    split_id: Mapped[str] = mapped_column(String(36), ForeignKey("splits.id"), nullable=False)
    split_name: Mapped[str] = mapped_column(String(128), nullable=False)

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
