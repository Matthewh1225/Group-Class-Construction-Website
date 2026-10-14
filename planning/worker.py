"""Run with: python -m planning.worker (separate from the Flask server)."""

import argparse
import time
import uuid

from dotenv import load_dotenv

# Load configuration before importing the provider clients.
load_dotenv()

from .jobs import LeaseLost, claim_job, save_job
from .workflow import StageError, run_workflow


def process_one(worker=None):
    worker = worker or uuid.uuid4().hex
    job = claim_job(worker)
    if job is None:
        return None

    def checkpoint(value):
        save_job(value, worker)

    try:
        run_workflow(job, checkpoint)
    except StageError as error:
        job["status"] = "failed"
        job["error"] = str(error)
        checkpoint(job)
    except LeaseLost:
        # Cancellation or an expired lease prevents this worker from saving again.
        return job["id"]
    except Exception:
        job["status"] = "failed"
        job["error"] = "The worker could not finish this job. Completed stages were preserved."
        checkpoint(job)
    return job["id"]


def main():
    parser = argparse.ArgumentParser(description="Process durable BuildBetter planner jobs.")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job.")
    options = parser.parse_args()
    worker = uuid.uuid4().hex
    while True:
        job_id = process_one(worker)
        if job_id:
            print(f"Processed planner job {job_id}", flush=True)
        if options.once:
            break
        if job_id is None:
            time.sleep(2)


if __name__ == "__main__":
    main()
