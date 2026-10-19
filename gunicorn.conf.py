"""Render starts the planner after Gunicorn loads the web application."""

import logging
import os
from threading import Event, Thread

bind = "0.0.0.0:" + os.getenv("PORT", "8000")
workers = 1
threads = 4
accesslog = "-"
errorlog = "-"


def _embedded_enabled():
    # Render sets RENDER=true.
    value = os.getenv("PLANNER_EMBEDDED_WORKER", os.getenv("RENDER", "false"))
    return value.strip().lower() == "true"


def post_worker_init(worker):
    if not _embedded_enabled():
        return
    if worker.cfg.workers != 1:
        raise RuntimeError("The embedded planner requires Gunicorn --workers 1.")
    existing = getattr(worker, "planner_thread", None)
    if existing is not None and existing.is_alive():
        return

    # Import after app initialization and fork, so environment/client setup is ready.
    from planning.worker import run_worker

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("planning.worker").setLevel(logging.INFO)
    worker.planner_stop = Event()
    worker.planner_thread = Thread(
        target=run_worker,
        kwargs={"stop_event": worker.planner_stop},
        name="planner-worker",
        daemon=True,
    )
    worker.planner_thread.start()
    worker.log.info("Started embedded planner worker.")


def worker_exit(server, worker):
    stop_event = getattr(worker, "planner_stop", None)
    if stop_event is None:
        return
    stop_event.set()
    # Idle workers stop immediately
    worker.planner_thread.join(timeout=5)
    if worker.planner_thread.is_alive():
        worker.log.info("Planner is still finishing a call; interrupted jobs recover after lease expiry.")
