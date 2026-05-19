"""SQLAlchemy ORM models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
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


class PantherRun(Base):
    __tablename__ = "panther_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(64), nullable=False)
    features_dir: Mapped[str] = mapped_column(String, nullable=False)
    source_csv: Mapped[str] = mapped_column(String, nullable=False)

    train_pct: Mapped[float] = mapped_column(Float, nullable=False)
    val_pct: Mapped[float] = mapped_column(Float, nullable=False)
    test_pct: Mapped[float] = mapped_column(Float, nullable=False)
    n_chunks: Mapped[int] = mapped_column(Integer, nullable=False)

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

    # JSON-encoded {"train": N, "val": N, "test": N, "unused": N, "total": N}
    split_counts: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
