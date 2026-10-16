

import argparse
import logging
import sqlite3
import time
import uuid

from dotenv import load_dotenv

load_dotenv()

from .jobs import LeaseLost, claim_job, database_path, save_job
from .workflow import StageError, run_workflow

logger = logging.getLogger(__name__)

# Seconds to wait after an error,
ERROR_DELAY = 10


def mark_failed(job, worker, message):
    job["status"] = "failed"
    job["error"] = message
    try:
        save_job(job, worker)
    except LeaseLost:
        # Cancellation or another worker claiming the job prevents this save.
        logger.info("Planner job %s was cancelled before its failure could be saved.", job["id"])


def process_one(worker=None):
    worker = worker or uuid.uuid4().hex
    job = claim_job(worker)
    if job is None:
        return None

    def checkpoint(value):
        save_job(value, worker)

    try:
        run_workflow(job, checkpoint)
    except LeaseLost:
        # Cancellation or an expired lease prevents  worker from saving again.
        logger.info("Planner job %s was cancelled or reclaimed; stopping work on it.", job["id"])
    except StageError as error:
        mark_failed(job, worker, str(error))
    except sqlite3.Error:
        # Leave the job "running" so its lease expires and claim_job puts it back in the queue 
        raise
    except Exception:
        logger.exception("Planner job %s stopped with an unexpected error.", job["id"])
        mark_failed(job, worker, "The worker could not finish this job. Completed stages were preserved.")
    return job["id"]


def safe_process_one(worker):
    try:
        return process_one(worker)
    except Exception:
        logger.exception("Planner worker error. Trying again in %s seconds.", ERROR_DELAY)
        time.sleep(ERROR_DELAY)
        return None


def main():
    parser = argparse.ArgumentParser(description="Process durable BuildBetter planner jobs.")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job.")
    options = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # The website and the worker must watch the same file, or jobs stay "Queued for planning".
    # DATABASE_ENV=test selects the test file, so start both with the same setting.
    logger.info("Watching planner jobs in %s", database_path())
    worker = uuid.uuid4().hex
    while True:
        job_id = safe_process_one(worker)
        if job_id:
            logger.info("Processed planner job %s", job_id)
        if options.once:
            break
        if job_id is None:
            time.sleep(2)


if __name__ == "__main__":
    main()
