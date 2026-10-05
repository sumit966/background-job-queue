"""Job type registry: implement what each job type actually does."""
import time
import random
from typing import Any, Dict


def task_send_email(payload: Dict[str, Any]) -> Dict[str, Any]:
    time.sleep(0.2)
    to = payload.get("to", "unknown@example.com")
    subject = payload.get("subject", "no subject")
    return {"sent_to": to, "subject": subject, "status": "sent"}


def task_process_image(payload: Dict[str, Any]) -> Dict[str, Any]:
    time.sleep(0.3)
    url = payload.get("url", "")
    return {"processed_url": url, "width": 1024, "height": 768}


def task_generate_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    time.sleep(0.5)
    rows = payload.get("rows", 100)
    return {"report_id": random.randint(1000, 9999), "rows_processed": rows}


def task_flaky(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Intentional 50% failure to demo retry logic."""
    if random.random() < 0.5:
        raise RuntimeError("Simulated transient failure")
    return {"status": "success"}


TASKS = {
    "send_email": task_send_email,
    "process_image": task_process_image,
    "generate_report": task_generate_report,
    "flaky": task_flaky,
}


def get_task(job_type: str):
    return TASKS.get(job_type)
