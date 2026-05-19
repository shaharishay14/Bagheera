"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

PatchEncoder = Literal["uni_v1", "uni_v2", "phikon", "phikon_v2"]
PantherMode = Literal["faiss", "kmeans"]

DATASET_NAME_PATTERN = r"^[A-Za-z0-9_-]+$"


# --- TRIDENT --------------------------------------------------------------

class TridentRunRequest(BaseModel):
    dataset_name: str = Field(..., pattern=DATASET_NAME_PATTERN, min_length=1, max_length=64)
    wsi_dir: str = Field(..., min_length=1)
    patch_encoder: PatchEncoder


class TridentRunResponse(BaseModel):
    id: str
    created_at: datetime
    dataset_name: str
    wsi_dir: str
    patch_encoder: str
    mag: int
    patch_size: int
    command: str
    status: str
    stdout: str
    stderr: str
    output_dir: str
    return_code: Optional[int]

    model_config = {"from_attributes": True}


# --- PANTHER --------------------------------------------------------------

class PantherRunRequest(BaseModel):
    dataset_name: str = Field(..., pattern=DATASET_NAME_PATTERN, min_length=1, max_length=64)
    features_dir: str = Field(..., min_length=1)
    source_csv: str = Field(..., min_length=1)

    # split
    train_pct: float = Field(..., ge=0, le=100)
    val_pct: float = Field(..., ge=0, le=100)
    test_pct: float = Field(..., ge=0, le=100)
    n_chunks: int = Field(..., ge=2)

    # panther
    mode: PantherMode = "faiss"
    in_dim: int = Field(1024, ge=1)
    n_proto_patches: int = Field(1_000_000, ge=1)
    n_proto: int = Field(16, ge=1)
    n_init: int = Field(5, ge=1)
    seed: int = Field(1, ge=0)
    num_workers: int = Field(10, ge=0)


class SplitCounts(BaseModel):
    train: int
    val: int
    test: int
    unused: int
    total: int


class PantherRunResponse(BaseModel):
    id: str
    created_at: datetime
    dataset_name: str
    features_dir: str
    source_csv: str
    train_pct: float
    val_pct: float
    test_pct: float
    n_chunks: int
    mode: str
    in_dim: int
    n_proto_patches: int
    n_proto: int
    n_init: int
    seed: int
    num_workers: int
    command: str
    status: str
    stdout: str
    stderr: str
    return_code: Optional[int]
    split_counts: SplitCounts

    model_config = {"from_attributes": True}


# --- filesystem -----------------------------------------------------------

class FsEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: Optional[int]
    mtime: Optional[datetime]


class FsListResponse(BaseModel):
    path: str
    parent: Optional[str]
    entries: list[FsEntry]
    is_root: bool


class FsRootsResponse(BaseModel):
    roots: list[str]


class FsCsvCountResponse(BaseModel):
    rows: int
