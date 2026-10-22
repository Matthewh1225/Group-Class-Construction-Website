

import argparse
import logging
import sqlite3
from threading import Event
import uuid

from dotenv import load_dotenv

load_dotenv()

from .jobs import LeaseLost, claim_job, database_path, save_job, stop_running_stages
from .schemas import PlanningError
from .workflow import run_workflow

logger = logging.getLogger(__name__)

IDLE_DELAY = 2    # seconds between checks
ERROR_DELAY = 10  # seconds after an error


def mark_failed(job, worker, message):
    job["status"] = "failed"
    job["error"] = message
    stop_running_stages(job, "failed")
    try:
        save_job(job, worker)
    except LeaseLost:
        logger.info("Planner job %s was cancelled before its failure could be saved.", job["id"])


def process_one(worker):
    job = claim_job(worker)
    if job is None:
        return None

    def save_progress(value):
        save_job(value, worker)

    try:
        run_workflow(job, save_progress)
    except LeaseLost:
        logger.info("Planner job %s was cancelled or reclaimed; stopping work on it.", job["id"])
    except PlanningError as error:
        mark_failed(job, worker, str(error))
    except sqlite3.Error:
        # The job will be marked interrupted when its time limit runs out.
        raise
    except Exception:
        logger.exception("Planner job %s stopped with an unexpected error.", job["id"])
        mark_failed(job, worker, "Planning stopped because of an unexpected error.")
    return job["id"]


def run_worker(stop_event=None, once=False):
    if stop_event is None:
        stop_event = Event()
    logger.info("Watching planner jobs in %s", database_path())
    worker = uuid.uuid4().hex

    while not stop_event.is_set():
        try:
            job_id = process_one(worker)
        except Exception:
            logger.exception("Planner worker error. Trying again in %s seconds.", ERROR_DELAY)
            if once:
                break
            stop_event.wait(ERROR_DELAY)
            continue

        if job_id is not None:
            logger.info("Processed planner job %s", job_id)
        if once:
            break
        if job_id is None:
            stop_event.wait(IDLE_DELAY)

    logger.info("Planner worker stopped.")


def main():
    parser = argparse.ArgumentParser(description="Process durable BuildBetter planner jobs.")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job.")
    options = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        run_worker(once=options.once)
    except KeyboardInterrupt:
        logger.info("Planner worker interrupted.")


if __name__ == "__main__":
    main()
