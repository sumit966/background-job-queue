"""Worker loop: pops jobs from the queue and executes them."""
import os
import time
import signal
import sys
from typing import Optional

from storage import init_db, claim_next_job, complete_job, fail_job
from tasks import get_task


POLL_INTERVAL = float(os.getenv("WORKER_POLL_INTERVAL", "1.0"))


_running = True


def _stop(signum, frame):
    global _running
    _running = False
    print("[Worker] Stopping gracefully...")
    sys.exit(0)


def process_one() -> bool:
    """Claim and process one job. Returns True if a job was processed."""
    job = claim_next_job()
    if not job:
        return False

    print(f"[Worker] Processing job {job['id']} type={job['job_type']}")
    func = get_task(job["job_type"])
    if func is None:
        fail_job(job["id"], f"Unknown job type: {job['job_type']}")
        print(f"[Worker] Job {job['id']} failed: unknown type")
        return True

    try:
        result = func(job["payload"])
        complete_job(job["id"], result)
        print(f"[Worker] Job {job['id']} completed")
    except Exception as e:
        fail_job(job["id"], str(e))
        print(f"[Worker] Job {job['id']} failed: {e}")
    return True


def run_worker(poll_interval: float = POLL_INTERVAL):
    """Continuous worker loop."""
    init_db()
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    print(f"[Worker] Started (poll={poll_interval}s)")
    while _running:
        try:
            processed = process_one()
            if not processed:
                time.sleep(poll_interval)
        except Exception as e:
            print(f"[Worker] Unexpected error: {e}")
            time.sleep(poll_interval)


if __name__ == "__main__":
    run_worker()
