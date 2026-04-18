from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------- Inference ----------
class InferenceRequest(BaseModel):
    dataset_id: str = Field(min_length=1)
    num_clusters: int = Field(ge=2, le=32)
    encoder: Literal["uni", "ctranspath", "resnet50"] = "uni"
    em_iter: int = Field(ge=1, le=10, default=1)
    tau: float = Field(ge=0.01, le=10.0, default=1.0)
    out_type: Literal["allcat", "weight_avg_mean", "weight_avg_all"] = "allcat"


class InferenceResponse(BaseModel):
    job_id: str
    status: Literal["Queued"]


# ---------- Jobs ----------
class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    num_clusters: int
    status: str
    priority: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    encoder: str = "uni"
    em_iter: int = 1
    tau: float = 1.0
    out_type: str = "allcat"


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int


class ReorderRequest(BaseModel):
    ordered_job_ids: list[str]


class ReorderResponse(BaseModel):
    ordered_job_ids: list[str]
    message: str = "Reordered"


# ---------- Annotations ----------
class AnnotationRequest(BaseModel):
    target_id: str = Field(min_length=1)
    target_type: Literal["slide", "cluster"]
    note: str = Field(min_length=1)


class AnnotationResponse(BaseModel):
    annotation_id: str
    message: str = "Saved"


class AnnotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotation_id: str
    target_id: str
    target_type: str
    note: str
    created_at: datetime


# ---------- Visualization ----------
class VisualizationCluster(BaseModel):
    cluster_id: str
    label: str | None
    patches: list[str]
    prototype_index: int


class VisualizationResponse(BaseModel):
    job_id: str
    dataset_id: str
    num_clusters: int
    encoder: str
    em_iter: int
    tau: float
    out_type: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    clusters: list[VisualizationCluster]
