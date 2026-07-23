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
    # "kfold" → K-fold CV (requires k>=2); "single" → one 100%-train fold (k ignored).
    kind: Literal["kfold", "single"] = "kfold"
    # Only meaningful for kind="kfold". Defaulted so a single-split request can omit it.
    k: int = Field(2, ge=2)
    seed: int = Field(1, ge=0)


# --- PANTHER --------------------------------------------------------------

class PantherKFoldRunRequest(BaseModel):
    """Async-mode kickoff payload. Returns immediately with {group_id, job_id};
    the actual K subprocesses run inside the background worker thread.
    """

    # The user-typed name. Stored on model_groups.display_name; each fold model
    # gets `{model_name}_k{i}_{rand8}` as its unique technical name.
    model_name: str = Field(..., pattern=MODEL_NAME_PATTERN, min_length=1, max_length=128)
    features_dir: str = Field(..., min_length=1)

    # Resolved server-side from features_dir → trident_run; the request still
    # carries it for client-side validation and to bind the right Split row.
    dataset_name: str = Field(..., pattern=DATASET_NAME_PATTERN, min_length=1, max_length=64)
    # Must reference an existing splits row (creation moved to POST /api/splits).
    split_id: str = Field(..., min_length=1)

    # PANTHER hyperparameters
    mode: PantherMode = "faiss"
    in_dim: int = Field(1024, ge=1)
    n_proto_patches: int = Field(1_000_000, ge=1)
    n_proto: int = Field(16, ge=1)
    n_init: int = Field(5, ge=1)
    # PANTHER --seed (k-means / faiss init).
    seed: int = Field(1, ge=0)
    num_workers: int = Field(10, ge=0)


class PantherSingleRunRequest(BaseModel):
    """Kickoff payload for a standalone single PANTHER model (no K-fold, no group).

    The referenced split must be a single ("100% train") split; every row lives
    in its k=0/train.csv. Returns immediately with {model_id, job_id}; the single
    subprocess runs inside the background worker thread.
    """

    # The user-typed name. Stored on the Model's base_name/display_name; the
    # unique technical name is `{model_name}_{rand8}` (no `_k{i}` suffix).
    model_name: str = Field(..., pattern=MODEL_NAME_PATTERN, min_length=1, max_length=128)
    features_dir: str = Field(..., min_length=1)

    dataset_name: str = Field(..., pattern=DATASET_NAME_PATTERN, min_length=1, max_length=64)
    # Must reference an existing (single) splits row.
    split_id: str = Field(..., min_length=1)

    # PANTHER hyperparameters
    mode: PantherMode = "faiss"
    in_dim: int = Field(1024, ge=1)
    n_proto_patches: int = Field(1_000_000, ge=1)
    n_proto: int = Field(16, ge=1)
    n_init: int = Field(5, ge=1)
    seed: int = Field(1, ge=0)
    num_workers: int = Field(10, ge=0)


class PantherSingleRunStartResponse(BaseModel):
    model_id: str
    job_id: str
    split_id: str
    split_name: str


class ModelInfo(BaseModel):
    id: str
    created_at: datetime
    base_name: str
    model_name: str
    display_name: str = ""
    group_id: str
    fold_index: int
    fold_k: int
    # "single" for standalone runs (group_id == id, fold_index=0, fold_k=1);
    # null for legacy K-fold folds.
    run_kind: Optional[str] = None
    dataset_name: str
    features_dir: str
    trident_run_id: Optional[str] = None
    split_id: str
    split_name: str
    split_dir_abs: str = ""
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
    is_favorite: bool = False
    viz_status: str = "pending"
    preview_slide_ids: Optional[list[str]] = None
    preview_heatmap_paths: Optional[list[str]] = None
    topk_grid_path: Optional[str] = None
    topk_per_proto: int = 3
    umap_path: Optional[str] = None
    # Analysis-page artifacts, parsed from the model's viz_artifacts JSON column.
    # Currently holds {"section_a": {...}}; null until viz has rendered it.
    viz_artifacts: Optional[dict] = None

    model_config = {"from_attributes": True}


# --- Datasets (Model Comparison page) -------------------------------------

class DatasetSummary(BaseModel):
    """One dataset that has at least one non-legacy (run_kind="single") model."""
    dataset_name: str
    model_count: int  # number of single (non-legacy) models for this dataset
    # slide_count is deferred to the /slides endpoint (enumerating h5s is not
    # free); left null here so the list stays cheap.
    slide_count: Optional[int] = None


class DatasetSlide(BaseModel):
    slide_id: str  # the h5 file stem
    wsi_path: Optional[str] = None  # resolved WSI path, or null if not found
    has_wsi: bool = False
    thumbnail_url: Optional[str] = None  # /api/slide-thumbnail?... when wsi_path resolved


class DatasetSlidesResponse(BaseModel):
    dataset_name: str
    features_dir: str
    wsi_dir: Optional[str] = None
    slides: list[DatasetSlide]
    slide_count: int
    # F3 early-signal: how many slides have a TRIDENT-written thumbnail on disk.
    thumbnails_found: int
    note: Optional[str] = None  # set when features_dir is missing/unreadable


class ModelGroupInfo(BaseModel):
    id: str
    created_at: datetime
    display_name: str
    dataset_name: str
    trident_run_id: Optional[str]
    k: int
    split_id: str

    model_config = {"from_attributes": True}


class ModelGroupSummary(BaseModel):
    """Aggregated fold counts for the Models card grid."""
    total: int
    ready: int
    failed: int
    running: int
    favorited: int


class ModelGroupListItem(BaseModel):
    id: str
    created_at: datetime
    display_name: str
    dataset_name: str
    trident_run_id: Optional[str]
    k: int
    split_id: str
    split_name: str
    mode: str
    n_proto: int
    summary: ModelGroupSummary


class ModelGroupDetail(BaseModel):
    group: ModelGroupListItem
    models: list[ModelInfo]
    split: SplitInfo


class ModelPatch(BaseModel):
    is_favorite: Optional[bool] = None
    display_name: Optional[str] = None


class ModelGroupPatch(BaseModel):
    display_name: Optional[str] = None


class ModelGroupDeleteResponse(BaseModel):
    group_id: str
    models_deleted: int
    inferences_deleted: int
    inference_notes_deleted: int
    inference_batches_deleted: int
    prototype_labels_deleted: int
    model_notes_deleted: int
    panther_runs_deleted: int
    dirs_removed: list[str]


class TridentParamsResponse(BaseModel):
    trident_run_id: Optional[str]
    patch_encoder: Optional[str]
    mag: Optional[int]
    patch_size: Optional[int]
    gpus: Optional[str] = None
    # e.g. "20x_256px_0px_overlap" — the per-mag/patch_size subdir TRIDENT writes.
    expected_features_dir_name: Optional[str]


class ShufflePreviewResponse(BaseModel):
    model_id: str
    preview_slide_ids: list[str]
    job_id: Optional[str] = None


class RenderSlideRequest(BaseModel):
    slide_id: str


class RenderSlideResponse(BaseModel):
    # "ready" (cache hit — artifacts populated), or "rendering" (job enqueued —
    # job_id populated; poll /api/jobs with ref_table=models for progress).
    status: str
    artifacts: Optional[dict] = None
    job_id: Optional[str] = None


class SlideVizResponse(BaseModel):
    # "ready" (manifest present — artifacts populated) or "missing".
    status: str
    artifacts: Optional[dict] = None


class SelectRoiRequest(BaseModel):
    # Manual point-based ROI pick. `slide_id=None` targets the Section A preview
    # slide (persisted onto viz_artifacts.section_a); a `slide_id` targets that
    # Compare slide (persisted onto its compare/{slide_id}/manifest.json). fx/fy
    # are floats in [0,1] normalized over the natural assignment-map image; the
    # route clamps them server-side.
    slide_id: Optional[str] = None
    fx: float
    fy: float


# --- Prototype labels --------------------------------------------------

class PrototypeLabelInfo(BaseModel):
    id: str
    model_id: str
    prototype_index: int
    label: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PrototypeLabelUpsert(BaseModel):
    model_id: str
    prototype_index: int = Field(..., ge=0)
    label: str = Field(..., max_length=500)


# --- Model notes -------------------------------------------------------

class ModelNoteInfo(BaseModel):
    id: str
    model_id: str
    body: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ModelNoteCreate(BaseModel):
    model_id: str
    body: str = Field(..., min_length=1)


class ModelNotePatch(BaseModel):
    body: str = Field(..., min_length=1)


# --- Inferences --------------------------------------------------------

InferenceStatus = Literal[
    "queued", "running_trident", "running_viz", "ready", "failed"
]


class InferenceInfo(BaseModel):
    id: str
    created_at: datetime
    finished_at: Optional[datetime]
    model_id: str
    batch_id: Optional[str]
    wsi_path: str
    wsi_filename: str
    wsi_mtime: float
    wsi_size: int
    wsi_hash: str
    output_dir: str
    features_h5_path: Optional[str]
    heatmap_path: Optional[str]
    mixture_plot_path: Optional[str]
    example_patches_dir: Optional[str]
    tsne_path: Optional[str]
    status: str
    error_message: Optional[str]

    model_config = {"from_attributes": True}


class InferenceBatchInfo(BaseModel):
    id: str
    created_at: datetime
    model_id: str
    user_label: Optional[str]
    total_count: int

    model_config = {"from_attributes": True}


class InferenceCreateRequest(BaseModel):
    model_id: str = Field(..., min_length=1)
    wsi_paths: list[str] = Field(..., min_length=1, max_length=200)
    batch_label: Optional[str] = Field(None, max_length=160)
    # When true, the server creates a fresh inference row even if a cache hit
    # would have served. Always paired per-path on the UI side; the request
    # carries a single flag that applies to every path in this submission.
    rerun: bool = False


class InferenceDispatchEntry(BaseModel):
    wsi_path: str
    status: str  # one of InferenceStatus, plus "rejected" for validation failures
    id: Optional[str] = None
    cached: bool = False
    message: Optional[str] = None


class InferenceCreateResponse(BaseModel):
    batch_id: Optional[str]
    inferences: list[InferenceDispatchEntry]


class InferenceLookupResponse(InferenceInfo):
    pass


class InferenceRerunResponse(BaseModel):
    new_inference_id: str
    job_id: str


# --- Inference notes ---------------------------------------------------


class InferenceNoteInfo(BaseModel):
    id: str
    inference_id: str
    body: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InferenceNoteCreate(BaseModel):
    inference_id: str
    body: str = Field(..., min_length=1)


class InferenceNotePatch(BaseModel):
    body: str = Field(..., min_length=1)


class ExamplePatchGroup(BaseModel):
    prototype_index: int
    label: Optional[str] = None
    urls: list[str]


class ExamplePatchesResponse(BaseModel):
    inference_id: str
    base_dir: str
    groups: list[ExamplePatchGroup]


# --- Run resolution ----------------------------------------------------

class RunResolveResponse(BaseModel):
    trident_run_id: str
    dataset_name: str
    output_dir: str
    patch_encoder: str
    mag: int
    patch_size: int
    # PANTHER --in_dim derived from the encoder (uni_v2→1536, uni_v1→1024,
    # phikon*→768). None if the encoder is unknown. The PANTHER form uses this to
    # auto-fill the input-dimension field so it can't be set wrong.
    in_dim: Optional[int] = None


class PantherKFoldStartResponse(BaseModel):
    group_id: str
    job_id: str
    k: int
    split_id: str
    split_name: str
    model_ids: list[str]


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


class FsCsvInspectResponse(BaseModel):
    rows: int
    columns: list[str]
    has_slide_id: bool
    slide_id_column: Optional[str]
    tif_count: int
    sample_ids: list[str]


# --- Jobs ----------------------------------------------------------------

JobType = Literal["panther_train", "post_train_viz", "inference"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]


class JobInfo(BaseModel):
    id: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    job_type: str
    ref_table: str
    ref_id: str
    status: str
    error_message: Optional[str]
    log_path: Optional[str]
    queue_position: Optional[int] = None

    model_config = {"from_attributes": True}


class JobDetail(JobInfo):
    log_tail: str = ""


# --- Queue ---------------------------------------------------------------


class JobView(BaseModel):
    """A job enriched with a human-readable title/subtitle for the Queue page."""

    id: str
    job_type: str
    status: str
    ref_table: str
    ref_id: str
    queue_position: Optional[int]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error_message: Optional[str]
    title: str
    subtitle: Optional[str] = None


class QueueResponse(BaseModel):
    running: Optional[JobView]
    waiting: list[JobView]
    recent: list[JobView]


class QueueReorderRequest(BaseModel):
    # Desired order of the waiting jobs (front first). Ids no longer queued
    # are ignored; queued ids omitted here are appended after, prior order kept.
    ordered_job_ids: list[str]
