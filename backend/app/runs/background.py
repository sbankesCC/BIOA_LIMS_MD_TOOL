"""Background processing: runs the graph for new runs in a worker thread, one run at a time.

Pilot infrastructure (ARCHITECTURE §11), not durable: a run still processing when the app stops
keeps its last status. Tests wait for the queue with `wait_for_all`.
"""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from threading import Lock
from typing import Protocol

# A job takes no arguments and handles its own errors (the graph marks a broken run failed)
Job = Callable[[], None]

# One worker: runs share the SQLite checkpoint file, so they are processed one after another
WORKER_COUNT = 1
THREAD_NAME = "run-processing"


class TaskRunner(Protocol):
    """Runs jobs in the background."""

    def submit(self, job: Job) -> None:
        """Queue a job to run in the background."""
        ...


class ThreadTaskRunner:
    """Runs jobs in a worker thread, in the order they were submitted."""

    def __init__(self) -> None:
        """Start the worker pool; it is stopped by `shutdown`."""
        self.executor = ThreadPoolExecutor(max_workers=WORKER_COUNT, thread_name_prefix=THREAD_NAME)
        self.futures: list[Future[None]] = []
        self.lock = Lock()

    def submit(self, job: Job) -> None:
        """Queue a job; an error it raises is kept in its future, never lost in the thread."""
        with self.lock:
            self.futures = [future for future in self.futures if not future.done()]
            self.futures.append(self.executor.submit(job))

    def wait_for_all(self, timeout_seconds: float | None = None) -> None:
        """Block until every queued job has finished (used by tests and at shutdown)."""
        with self.lock:
            pending = list(self.futures)
        wait(pending, timeout=timeout_seconds)

    def shutdown(self) -> None:
        """Stop taking jobs; queued jobs that have not started are dropped."""
        self.executor.shutdown(wait=False, cancel_futures=True)
