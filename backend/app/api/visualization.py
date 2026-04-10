import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Cluster, Job
from app.schemas import VisualizationCluster, VisualizationResponse

router = APIRouter(prefix="/api/v1", tags=["visualization"])


@router.get("/visualization/{job_id}", response_model=VisualizationResponse)
def get_visualization(job_id: str, db: Session = Depends(get_db)) -> VisualizationResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    rows = db.query(Cluster).filter(Cluster.job_id == job_id).all()
    clusters = [
        VisualizationCluster(cluster_id=c.id, patches=json.loads(c.patches_json))
        for c in rows
    ]
    return VisualizationResponse(clusters=clusters)
