"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

PatchEncoder = Literal["uni_v1", "uni_v2", "phikon", "phikon_v2"]
PantherMode = Literal["faiss", "kmeans"]

DATASET_NAME_PATTERN = r"^[A-Za-z0-9_-]+$"
MODEL_NAME_PATTERN = r"^[A-Za-z0-9_-]+$"


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


# --- Splits ---------------------------------------------------------------

class FoldCountsSchema(BaseModel):
    train: int
    val: int
    test: int


class SplitInfo(BaseModel):
    id: str
    created_at: datetime
    dataset_name: str
    split_name: str
    abs_path: str
    source_csv: str
    k: int
    seed: int
    total_rows: int
    per_fold_counts: list[FoldCountsSchema]

    model_config = {"from_attributes": True}


class CreateSplitRequest(BaseModel):
    dataset_name: str = Field(..., pattern=DATASET_NAME_PATTERN, min_length=1, max_length=64)
    source_csv: str = Field(..., min_length=1)
    k: int = Field(..., ge=2)
    seed: int = Field(1, ge=0)


# --- PANTHER --------------------------------------------------------------

class PantherKFoldRunRequest(BaseModel):
    # Required core
    model_name: str = Field(..., pattern=MODEL_NAME_PATTERN, min_length=1, max_length=128)
    features_dir: str = Field(..., min_length=1)

    # Split selection: caller provides EITHER an existing split_name, OR (source_csv + k + split_seed)
    # to create one inline. dataset_name is required either way (used for grouping splits on disk).
    dataset_name: str = Field(..., pattern=DATASET_NAME_PATTERN, min_length=1, max_length=64)
    split_name: Optional[str] = None
    source_csv: Optional[str] = None
    k: Optional[int] = Field(None, ge=2)
    # Splitter seed — only used when creating a split inline. Unrelated to the PANTHER --seed below.
    split_seed: Optional[int] = Field(None, ge=0)

    # PANTHER hyperparameters
    mode: PantherMode = "faiss"
    in_dim: int = Field(1024, ge=1)
    n_proto_patches: int = Field(1_000_000, ge=1)
    n_proto: int = Field(16, ge=1)
    n_init: int = Field(5, ge=1)
    # PANTHER --seed (k-means / faiss init). Independent of split_seed.
    seed: int = Field(1, ge=0)
    num_workers: int = Field(10, ge=0)


class ModelInfo(BaseModel):
    id: str
    created_at: datetime
    base_name: str
    model_name: str
    group_id: str
    fold_index: int
    fold_k: int
    dataset_name: str
    features_dir: str
    split_id: str
    split_name: str
    mode: str
    in_dim: int
    n_proto_patches: int
    n_proto: int
    n_init: int
    seed: int
    num_workers: int
    status: str
    prototypes_dir: str
    prototype_files: list[str]

    model_config = {"from_attributes": True}


class PantherRunInfo(BaseModel):
    """Per-fold execution log entry."""

    id: str
    created_at: datetime
    group_id: str
    fold_index: int
    model_id: str
    dataset_name: str
    features_dir: str
    split_name: str
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

    model_config = {"from_attributes": True}


class FoldOutcome(BaseModel):
    fold_index: int
    model_id: str
    model_name: str
    status: str
    prototypes_dir: str
    prototype_files: list[str]
    return_code: Optional[int]
    stderr_tail: str = ""


class KFoldRunSummary(BaseModel):
    total: int
    succeeded: int
    failed: int


class PantherKFoldRunResponse(BaseModel):
    group_id: str
    split_id: str
    split_name: str
    k: int
    models: list[FoldOutcome]
    summary: KFoldRunSummary


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
