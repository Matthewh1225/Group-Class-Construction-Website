import argparse
import logging
from threading import Event, Thread
import uuid

from dotenv import load_dotenv
from mysql.connector import Error as DatabaseError

load_dotenv()

from .jobs import LeaseLost, claim_job, save_job, mark_processing_stages
from .schemas import PlanningError
from .workflow import run_workflow
from services.vector_search import load_vector_search, update_cache_if_needed
from utils.database import DatabaseBusyError

logger = logging.getLogger(__name__)

IDLE_DELAY = 2    # seconds between checks
ERROR_DELAY = 10  # seconds after an error


def mark_failed(job, worker, message):
    job["status"] = "failed"
    job["error"] = message
    mark_processing_stages(job, "failed")
    try:
        save_job(job, worker)
    except LeaseLost:
        logger.info("Planner job %s no longer belongs to this worker; its failure was not saved.", job["id"])


def process_one(worker):
    try:
        job = claim_job(worker)
    except DatabaseBusyError:
        # Another worker using the same database is checking the queue right now.
        logger.warning("Planner queue is busy; trying again shortly.")
        return None
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
    except DatabaseError:
        # The queue check marks expired jobs as failed.
        raise
    except Exception:
        logger.exception("Planner job %s stopped with an unexpected error.", job["id"])
        mark_failed(job, worker, "Planning stopped because of an unexpected error.")
    return job["id"]


def run_worker(stop_event=None, once=False, threads=1):
    if stop_event is None:
        stop_event = Event()
    # Rebuild missing or outdated vectors before taking jobs; failures fall back to SQL search.
    update_cache_if_needed()
    load_vector_search()
    # Extra threads share the model and cache, so a slow plan doesn't hold up the others.
    for number in range(2, threads + 1):
        Thread(target=watch_queue, args=(stop_event,), name=f"planner-worker-{number}", daemon=True).start()
    watch_queue(stop_event, once)


def watch_queue(stop_event, once=False):
    logger.info("Watching planner jobs in MySQL")
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
    parser = argparse.ArgumentParser(description="Run the BuildBetter planner worker.")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job.")
    parser.add_argument("--threads", type=int, default=1, help="How many jobs to plan at the same time.")
    options = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        run_worker(once=options.once, threads=options.threads)
    except KeyboardInterrupt:
        logger.info("Planner worker interrupted.")


if __name__ == "__main__":
    main()
