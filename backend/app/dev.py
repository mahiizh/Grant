"""Launch the FastAPI dev server and the ingestion worker together.

``make dev`` uses this module so one command still runs two processes:

* the API (uvicorn with reload)
* the uploaded-document ingestion worker

The processes stay separate. This module is only a small supervisor that starts
one worker, runs the API in the foreground, and stops the worker on exit.
"""

from __future__ import annotations

import atexit
import logging
import os
import subprocess
import sys

import uvicorn

logger = logging.getLogger("graphrag.dev")

_SUPERVISOR_ENV = "GRAPHRAG_DEV_SUPERVISOR"


def _stop_worker(worker: subprocess.Popen | None) -> None:
    """Terminate the worker if it is still running."""
    if worker is None or worker.poll() is not None:
        return
    logger.info("Stopping ingestion worker [pid=%s]...", worker.pid)
    worker.terminate()
    try:
        worker.wait(timeout=5)
    except subprocess.TimeoutExpired:
        worker.kill()
        worker.wait(timeout=5)


def _start_worker() -> subprocess.Popen | None:
    """Start one ingestion worker, unless this is a uvicorn reload child."""
    if os.getenv(_SUPERVISOR_ENV) == "1":
        return None

    env = os.environ.copy()
    env[_SUPERVISOR_ENV] = "1"
    worker = subprocess.Popen(
        [sys.executable, "-m", "app.workers.ingestion_worker"],
        cwd=os.getcwd(),
        env=env,
    )
    logger.info("Started ingestion worker [pid=%s]", worker.pid)
    atexit.register(_stop_worker, worker)
    return worker


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    worker = _start_worker()
    # Uvicorn's reload subprocess re-imports this module; the marker prevents
    # it from starting a second worker.
    os.environ[_SUPERVISOR_ENV] = "1"

    try:
        logger.info("Starting API on http://0.0.0.0:8000")
        uvicorn.run(
            "app.main:app",
            reload=True,
            reload_dirs=["app"],
            host="0.0.0.0",
            port=8000,
        )
    finally:
        _stop_worker(worker)


if __name__ == "__main__":
    main()
