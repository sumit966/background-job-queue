"""FastAPI service exposing the job queue."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from storage import (
    init_db, enqueue_job, get_job, list_jobs, stats
)
from worker import process_one
from tasks import TASKS


app = FastAPI(
    title="Background Job Queue API",
    description="Async job queue with priorities, retries, and status tracking",
    version="1.0.0",
)


class EnqueueRequest(BaseModel):
    job_type: str = Field(..., min_length=1, max_length=50)
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(5, ge=1, le=10, description="Lower = higher priority")
    max_retries: int = Field(3, ge=0, le=10)


class JobResponse(BaseModel):
    id: int
    job_type: str
    payload: Dict[str, Any]
    status: str
    priority: int
    retries: int
    max_retries: int
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


@app.on_event("startup")
def startup():
    init_db()
    print("[OK] Database initialized")


@app.get("/")
def root():
    return {"message": "Background Job Queue API", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/task-types")
def task_types():
    return {"task_types": list(TASKS.keys())}


@app.post("/jobs", response_model=JobResponse)
def create_job(req: EnqueueRequest):
    if req.job_type not in TASKS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown job_type. Valid: {list(TASKS.keys())}"
        )
    jid = enqueue_job(req.job_type, req.payload, req.priority, req.max_retries)
    return get_job(jid)


@app.get("/jobs", response_model=List[JobResponse])
def list_jobs_endpoint(status: Optional[str] = None, limit: int = 50):
    return list_jobs(status=status, limit=limit)


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job_endpoint(job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/stats")
def stats_endpoint():
    return stats()


@app.post("/run-once")
def run_one(background: BackgroundTasks):
    """Trigger the worker to process at most one job now.

    Useful when you don't want a long-running worker process.
    """
    processed = process_one()
    return {"processed": processed}


@app.post("/run-until-empty")
def run_until_empty(background: BackgroundTasks, max_jobs: int = 100):
    """Process queued jobs until empty or max_jobs reached."""
    processed = 0
    for _ in range(max_jobs):
        if not process_one():
            break
        processed += 1
    return {"processed": processed}
