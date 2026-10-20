

import argparse
import logging
import sqlite3
from threading import Event
import time
import uuid

from dotenv import load_dotenv

load_dotenv()

from .jobs import LeaseLost, claim_job, database_path, save_job
from .workflow import PlanningError, run_workflow

logger = logging.getLogger(__name__)

ERROR_DELAY = 10


# Saves the job as "failed" with a short error message the user will see.
def mark_failed(job, worker, message):
    job["status"] = "failed"
    job["error"] = message
    try:
        save_job(job, worker)
    except LeaseLost:
        # Cancellation or another worker claiming the job prevents this save.
        logger.info("Planner job %s was cancelled before its failure could be saved.", job["id"])


# Takes one queued job and runs the whole workflow on it. A failure is saved on the job;
# the user can then start it again from the job page.
def process_one(worker=None, stop_event=None):
    worker = worker or uuid.uuid4().hex
    try:
        job = claim_job(worker)
        if job is None:
            return None

        def save_progress(value):
            save_job(value, worker)

        try:
            run_workflow(job, save_progress)
        except LeaseLost:
            # Cancellation or an expired lease prevents this worker from saving.
            logger.info("Planner job %s was cancelled or reclaimed; stopping work on it.", job["id"])
        except PlanningError as error:
            mark_failed(job, worker, str(error))
        except sqlite3.Error:
            # The job cannot be saved; when its lease runs out it is marked as interrupted (jobs.claim_job).
            raise
        except Exception:
            logger.exception("Planner job %s stopped with an unexpected error.", job["id"])
            mark_failed(job, worker, "Planning stopped because of an unexpected error.")
        return job["id"]
    except Exception:
        logger.exception("Planner worker error. Trying again in %s seconds.", ERROR_DELAY)
        if stop_event is None:
            time.sleep(ERROR_DELAY)
        else:
            stop_event.wait(ERROR_DELAY)
        return None


def run_worker(stop_event=None, once=False):
    stop_event = stop_event if stop_event is not None else Event()
    logger.info("Watching planner jobs in %s", database_path())
    worker = uuid.uuid4().hex
    try:
        while not stop_event.is_set():
            job_id = process_one(worker, stop_event)
            if job_id:
                logger.info("Processed planner job %s", job_id)
            if once:
                break
            if job_id is None:
                stop_event.wait(2)
    finally:
        logger.info("Planner worker stopped.")


# Starts the worker: keeps checking for queued planner jobs and running them 
def main():
    parser = argparse.ArgumentParser(description="Process durable BuildBetter planner jobs.")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job.")
    options = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # The website and the worker must watch the same file, or jobs stay "Queued for planning".
    # DATABASE_ENV=test selects the test file, so start both with the same setting.
    try:
        run_worker(once=options.once)
    except KeyboardInterrupt:
        logger.info("Planner worker interrupted.")


if __name__ == "__main__":
    main()
