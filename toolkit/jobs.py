"""Single worker thread that runs jobs one at a time and owns the iTunes COM connection."""
import itertools
import logging
import queue
import threading
import time
import traceback

from .itunes import ITunes
from .scan import Cancelled

log = logging.getLogger("toolkit")


class Job:
    _ids = itertools.count(1)

    def __init__(self, title, fn, kind="task", source="manual"):
        self.id = next(self._ids)
        self.title = title
        self.kind = kind
        self.source = source  # manual | auto
        self.fn = fn
        self.status = "queued"  # queued running done failed cancelled
        self.progress = None    # 0..1 or None (indeterminate)
        self.message = "Waiting to start"
        self.log = []
        self.result = None
        self.error = ""
        self.created = time.time()
        self.started = self.finished = None
        self._cancel = threading.Event()

    def to_dict(self, with_log=False):
        d = {k: getattr(self, k) for k in ("id", "title", "kind", "source", "status", "progress", "message",
                                           "error", "created", "started", "finished")}
        d["log_lines"] = len(self.log)
        if with_log:
            d["log"] = self.log[-2000:]
            d["result"] = self.result
        return d


class Context:
    """What a job function gets: progress reporting, logging, cancellation, iTunes."""

    def __init__(self, job, runner):
        self.job, self.runner = job, runner

    @property
    def itunes(self):
        return self.runner.itunes()

    def progress(self, done, total=None, message=None):
        if total is None:
            self.job.progress = done  # already a fraction or None
        else:
            self.job.progress = (done / total) if total else 1.0
        if message is not None:
            self.job.message = message

    def say(self, message, frac=None):
        self.job.message = message
        if frac is not None:
            self.job.progress = frac

    def log(self, line):
        self.job.log.append(line)

    def cancelled(self):
        return self.job._cancel.is_set()

    def check(self):
        if self.job._cancel.is_set():
            raise Cancelled()


class JobRunner:
    def __init__(self, on_finished=None):
        self.q = queue.Queue()
        self.jobs = []
        self.current = None
        self.on_finished = on_finished
        self._itunes = None
        self._ctx = None
        self.itunes_status = "not connected"
        threading.Thread(target=self._loop, name="jobs", daemon=True).start()

    def itunes(self):
        if self._itunes is None:
            self._itunes = ITunes(on_wait=lambda m: self._ctx and self._ctx.say(m))
        try:
            self._itunes.connect()
            self.itunes_status = f"connected (iTunes {self._itunes.version})"
        except Exception as e:
            self.itunes_status = f"cannot connect: {e}"
            raise
        return self._itunes

    def submit(self, title, fn, kind="task", source="manual"):
        job = Job(title, fn, kind, source)
        self.jobs.append(job)
        self.jobs = self.jobs[-50:]
        self.q.put(job)
        return job

    def busy(self):
        return self.current is not None or not self.q.empty()

    def has_pending(self, kind):
        return any(j.kind == kind and j.status in ("queued", "running") for j in self.jobs)

    def get(self, job_id):
        return next((j for j in self.jobs if j.id == job_id), None)

    def cancel(self, job_id):
        j = self.get(job_id)
        if j and j.status in ("queued", "running"):
            j._cancel.set()
            if j.status == "queued":
                j.status, j.message = "cancelled", "Cancelled before it started"
        return j

    def _refresh_itunes_view(self, job):
        it = self._itunes
        if it is None or not it.dirty or it.app is None:
            return
        try:
            job.message = "Refreshing the iTunes window..." if job.status == "running" else job.message
            if it.refresh_view():
                job.log.append("Refreshed the iTunes window so the changes show without restarting iTunes.")
        except Exception as e:
            log.warning("could not refresh the iTunes view: %s", e)
            job.log.append(f"Note: couldn't refresh the iTunes window ({e}). The changes are saved; "
                           "click another playlist in iTunes and back to see them.")

    def _loop(self):
        while True:
            job = self.q.get()
            if job.status == "cancelled":
                continue
            self.current = job
            self._ctx = ctx = Context(job, self)
            job.status, job.started, job.message = "running", time.time(), "Starting..."
            try:
                job.result = job.fn(ctx)
                job.status = "done"
                if job.progress is not None:
                    job.progress = 1.0
            except Cancelled:
                job.status, job.message = "cancelled", "Cancelled - work done so far was kept"
            except Exception as e:
                job.status, job.error = "failed", str(e) or e.__class__.__name__
                job.message = job.error
                job.log.append(traceback.format_exc())
                log.exception("job %s failed", job.title)
            finally:
                # Changes reached iTunes' database; make its window show them too.
                # Runs even after a cancel/failure, since earlier steps may have changed things.
                self._refresh_itunes_view(job)
                job.finished = time.time()
                self.current = self._ctx = None
                if self.on_finished:
                    try:
                        self.on_finished(job)
                    except Exception:
                        log.exception("on_finished")
