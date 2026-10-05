"""Tests for Background Job Queue API."""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200


def test_health():
    r = client.get("/health")
    assert r.status_code == 200


def test_task_types():
    r = client.get("/task-types")
    assert r.status_code == 200
    assert "task_types" in r.json()
    assert "send_email" in r.json()["task_types"]


def test_create_job():
    r = client.post("/jobs", json={
        "job_type": "send_email",
        "payload": {"to": "test@example.com", "subject": "Hello"},
        "priority": 3,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert body["job_type"] == "send_email"


def test_create_job_invalid_type():
    r = client.post("/jobs", json={"job_type": "unknown", "payload": {}})
    assert r.status_code == 400


def test_run_once_and_get():
    r = client.post("/jobs", json={
        "job_type": "generate_report",
        "payload": {"rows": 50},
    })
    jid = r.json()["id"]

    r = client.post("/run-once")
    assert r.status_code == 200

    r = client.get(f"/jobs/{jid}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("completed", "queued", "running")


def test_stats():
    r = client.get("/stats")
    assert r.status_code == 200
    assert "queued" in r.json()
