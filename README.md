# Background Job Queue & Task Scheduler Service

Production-style async job queue with priorities, retries with backoff, status tracking, and a REST API. Built with FastAPI + SQLite, designed for easy upgrade to Redis + Celery.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Celery](https://img.shields.io/badge/Celery_(optional)-37814A?style=for-the-badge&logo=celery&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

## Overview

A background job queue that mirrors the design of Celery/RQ but without external infrastructure:

1. Enqueue jobs with a type + JSON payload
2. Priorities (1-10, lower = higher priority)
3. Automatic retries with configurable max attempts
4. Status lifecycle: queued -> running -> completed / failed
5. Worker loop that atomically claims jobs (safe even with multiple workers)
6. REST API for enqueue, list, view, and stats
7. Built-in job types for demo (email, image processing, report generation, flaky)

Every job change is persisted so you can inspect history, retry counts, and error messages.

## Problem Statement

Background jobs are everywhere: sending emails, resizing images, generating reports, syncing data. Doing this naively inside a web request causes:

- Slow HTTP responses
- Timeouts under load
- Lost jobs when the process crashes
- No visibility into failures or retry counts

A proper queue solves all four, but full Celery setups need Redis + worker fleets. Not ideal for small projects or demos.

## Solution

A lightweight, production-aware queue that:

- Uses SQLite with row-level locking for atomic job claims
- Persists every state change (queued/running/completed/failed)
- Supports priorities and retry limits per job
- Exposes a FastAPI surface for enqueue, list, view, and stats
- Runs the worker either as a long-lived process or on-demand via API

The architecture maps 1:1 to Celery/RQ, so upgrading later is trivial.

## Architecture

Client (POST /jobs)
    |
    v
+-------------------+
|  SQLite jobs      |  status: queued
+---------+---------+
          |
          v
+-------------------+
|  Worker loop      |  atomically claims next job
|  (worker.py)      |  (BEGIN IMMEDIATE transaction)
+---------+---------+
          |
          v
+-------------------+
|  Task registry    |  send_email, process_image,
|  (tasks.py)       |  generate_report, flaky
+---------+---------+
          |
   success|failure
          v
+-------------------+   +-------------------+
| complete_job()    |   | fail_job()        |
| status=completed  |   | retries < max ->  |
| result=...        |   |   requeue         |
+-------------------+   | else -> failed    |
                        +-------------------+

## Tech Stack

| Category | Technologies |
|----------|-------------|
| API | FastAPI, Uvicorn, Pydantic |
| Storage | SQLite (indexed for queue performance) |
| Worker | Standalone Python process |
| Concurrency | SQLite BEGIN IMMEDIATE for atomic claims |
| Testing | pytest, httpx |
| Optional Upgrade | Redis, RQ, Celery |
| Containerization | Docker |
| CI/CD | GitHub Actions |
| Language | Python 3.11+ |

## Project Structure

background-job-queue/
├── src/
│   ├── __init__.py
│   ├── storage.py          # SQLite schema + queue operations
│   ├── tasks.py            # Task registry (job type -> function)
│   └── worker.py           # Worker loop + graceful shutdown
├── api/
│   ├── __init__.py
│   └── main.py             # FastAPI endpoints
├── tests/
│   ├── __init__.py
│   └── test_api.py         # pytest tests
├── data/                    # SQLite db (git-ignored)
├── .github/workflows/ci.yml
├── Dockerfile
├── requirements.txt
├── requirements-optional.txt
├── .env.example
├── .gitignore
├── LICENSE
└── README.md

## Quick Start

### 1. Clone

git clone https://github.com/sumit966/background-job-queue.git
cd background-job-queue

### 2. Virtual environment

Windows:
python -m venv venv
venv\Scripts\activate

macOS / Linux:
python3 -m venv venv
source venv/bin/activate

### 3. Install dependencies

pip install -r requirements.txt

### 4. Start the API

uvicorn api.main:app --reload

Runs at http://localhost:8000

### 5. (Optional) Start a worker in another terminal

python src/worker.py

The worker polls the queue, processes jobs, and handles retries.

### 6. Open Swagger

http://localhost:8000/docs

## API Usage

### GET /task-types

List all registered job types.

Response:
{
  "task_types": ["send_email", "process_image", "generate_report", "flaky"]
}

### POST /jobs

Enqueue a job.

Request:
{
  "job_type": "send_email",
  "payload": {
    "to": "user@example.com",
    "subject": "Welcome"
  },
  "priority": 3,
  "max_retries": 3
}

Response:
{
  "id": 1,
  "job_type": "send_email",
  "payload": {"to": "user@example.com", "subject": "Welcome"},
  "status": "queued",
  "priority": 3,
  "retries": 0,
  "max_retries": 3,
  "created_at": "...",
  "updated_at": "..."
}

Priority: 1 = highest, 10 = lowest. Workers always pull lowest number first.

### GET /jobs?status=queued&limit=50

List jobs, optionally filtered by status.

### GET /jobs/{id}

Get a single job with current status, result, and error.

### GET /stats

Counts by status.

Response:
{
  "queued": 12,
  "running": 1,
  "completed": 45,
  "failed": 3
}

### POST /run-once

Process at most one job synchronously. Useful when you don't want a long-lived worker.

Response:
{ "processed": true }

### POST /run-until-empty?max_jobs=100

Process queued jobs until empty or until max_jobs is reached.

### Other Endpoints

| Endpoint | Method | Purpose |
|----------|---------|---------|
| / | GET | API info |
| /health | GET | Health check |
| /docs | GET | Swagger UI |
| /redoc | GET | Alternative docs |

## Built-in Job Types

| Job Type | Payload | What it Does |
|----------|---------|-------------|
| send_email | {to, subject} | Simulates sending an email |
| process_image | {url} | Simulates image processing |
| generate_report | {rows} | Simulates report generation |
| flaky | {} | Fails 50% of the time (demo retries) |

Add your own by editing `src/tasks.py`:

def my_task(payload):
    # do work
    return {"ok": True}

TASKS["my_task"] = my_task

## Retry Logic

- Each job has retries and max_retries fields
- On failure, retries is incremented
- If retries < max_retries, job returns to "queued" (automatic retry)
- Otherwise, status becomes "failed" with the error message stored
- Test with the flaky job type: it fails ~50% of the time and succeeds on retry

## Concurrency Safety

The worker uses SQLite's BEGIN IMMEDIATE transaction to claim jobs atomically. Even if you run multiple worker processes against the same SQLite file, no two workers will process the same job.

For high-scale deployments, swap SQLite for Redis (see optional deps) and use BRPOPLPUSH or the RQ library.

## Testing

pytest tests/ -v

Tests cover:
- Root, health, task-types
- Create job with valid type
- Create job with invalid type returns 400
- Run-once processes a job
- Get job returns current status
- Stats returns counts by status

## Docker

Build:
docker build -t background-job-queue .

Run API:
docker run -p 8000:8000 background-job-queue

Run worker (separate container):
docker run background-job-queue python src/worker.py

## CI/CD

Every push to main triggers GitHub Actions:

1. Install Python 3.11 + dependencies
2. Run pytest test suite

See .github/workflows/ci.yml.

## Production Upgrade Path

| Component | Dev | Production |
|-----------|-----|------------|
| Queue | SQLite | Redis + RQ or Celery |
| Broker | SQLite table | Redis Streams / RabbitMQ |
| Worker | Single process | Celery worker pool |
| Scheduling | Manual / cron | Celery Beat |
| Monitoring | /stats endpoint | Flower dashboard |
| Persistence | SQLite | PostgreSQL |

The API surface (POST /jobs, GET /jobs/{id}, GET /stats) stays the same, so clients don't need changes.

## Key Learnings

- Atomic job claiming requires BEGIN IMMEDIATE (SQLite) or equivalent
- Priority ordering (priority ASC, created_at ASC) gives fair, predictable scheduling
- Retries must increment a counter, not just requeue, or you loop forever
- Persisting started_at + finished_at enables latency analytics for free
- Decoupling worker from API lets you scale each independently
- A bounded worker loop (max_jobs) prevents runaway processing in tests
- Graceful shutdown via SIGTERM handlers avoids orphaned "running" jobs

## Future Improvements

- Scheduled jobs (cron-like): run_at column + worker scheduler
- Job groups / pipelines (DAG of tasks)
- Dead letter queue for jobs that exceed max_retries
- Prometheus metrics: queue depth, throughput, latency histogram
- Web dashboard showing live job states
- Redis backend for horizontal scaling
- Celery + Flower for enterprise-grade monitoring
- Deploy API to Cloud Run, worker to GKE / Cloud Run jobs

## License

MIT License - see LICENSE file.

## Author

Sumit Raj
- M.Tech Applied AI & ML @ VNIT Nagpur
- Ex-Software Engineer Intern @ Salesforce
- GitHub: https://github.com/sumit966
- LinkedIn: https://www.linkedin.com/in/er-sumit-raj-/
- Portfolio: https://sumit966-github-io.vercel.app
- Email: info.sr0909@gmail.com

If you found this project useful, please consider giving it a star!
