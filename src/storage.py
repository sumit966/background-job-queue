"""SQLite storage for jobs (queue + status tracking)."""
import os
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any


DB_PATH = os.getenv("DATABASE_URL", "data/jobs.db").replace("sqlite:///", "")


def _connect():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = _connect()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            priority INTEGER NOT NULL DEFAULT 5,
            retries INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            result TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority DESC, created_at ASC)")
    con.commit()
    con.close()


def now_iso():
    return datetime.utcnow().isoformat()


def enqueue_job(job_type: str, payload: dict, priority: int = 5, max_retries: int = 3) -> int:
    con = _connect()
    cur = con.cursor()
    ts = now_iso()
    cur.execute(
        """INSERT INTO jobs (job_type, payload, status, priority, retries, max_retries, created_at, updated_at)
           VALUES (?, ?, 'queued', ?, 0, ?, ?, ?)""",
        (job_type, json.dumps(payload), priority, max_retries, ts, ts)
    )
    con.commit()
    jid = cur.lastrowid
    con.close()
    return jid


def get_job(job_id: int) -> Optional[Dict[str, Any]]:
    con = _connect()
    cur = con.cursor()
    cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    j = dict(row)
    j["payload"] = json.loads(j["payload"])
    if j.get("result"):
        try:
            j["result"] = json.loads(j["result"])
        except Exception:
            pass
    return j


def list_jobs(status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    con = _connect()
    cur = con.cursor()
    if status:
        cur.execute("SELECT * FROM jobs WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit))
    else:
        cur.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    for j in rows:
        j["payload"] = json.loads(j["payload"])
    return rows


def claim_next_job() -> Optional[Dict[str, Any]]:
    """Atomically pull the next queued job (highest priority, oldest first)."""
    con = _connect()
    cur = con.cursor()
    cur.execute("BEGIN IMMEDIATE")
    try:
        cur.execute(
            """SELECT * FROM jobs
               WHERE status = 'queued'
               ORDER BY priority ASC, created_at ASC
               LIMIT 1"""
        )
        row = cur.fetchone()
        if not row:
            con.execute("COMMIT")
            return None

        job_id = row["id"]
        cur.execute(
            "UPDATE jobs SET status = 'running', started_at = ?, updated_at = ? WHERE id = ?",
            (now_iso(), now_iso(), job_id)
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()

    return get_job(job_id)


def complete_job(job_id: int, result: dict):
    con = _connect()
    cur = con.cursor()
    cur.execute(
        """UPDATE jobs
           SET status = 'completed', result = ?, updated_at = ?, finished_at = ?
           WHERE id = ?""",
        (json.dumps(result), now_iso(), now_iso(), job_id)
    )
    con.commit()
    con.close()


def fail_job(job_id: int, error: str):
    """Mark job as failed or requeue if retries remain."""
    job = get_job(job_id)
    if not job:
        return

    retries = job["retries"] + 1
    if retries < job["max_retries"]:
        con = _connect()
        cur = con.cursor()
        cur.execute(
            """UPDATE jobs
               SET status = 'queued', retries = ?, error = ?, updated_at = ?
               WHERE id = ?""",
            (retries, error, now_iso(), job_id)
        )
        con.commit()
        con.close()
    else:
        con = _connect()
        cur = con.cursor()
        cur.execute(
            """UPDATE jobs
               SET status = 'failed', retries = ?, error = ?, updated_at = ?, finished_at = ?
               WHERE id = ?""",
            (retries, error, now_iso(), now_iso(), job_id)
        )
        con.commit()
        con.close()


def stats() -> Dict[str, int]:
    con = _connect()
    cur = con.cursor()
    cur.execute("SELECT status, COUNT(*) AS c FROM jobs GROUP BY status")
    counts = {row["status"]: row["c"] for row in cur.fetchall()}
    con.close()
    for s in ["queued", "running", "completed", "failed"]:
        counts.setdefault(s, 0)
    return counts
