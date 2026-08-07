import json
import os
import time

_LOG_PATH = os.path.join(os.path.dirname(__file__), "debug-2d1d49.log")
_SESSION_ID = "2d1d49"
_RUN_ID = "pre-fix"


class PerfTimer:
    def __init__(self, location, message, hypothesis_id, extra=None):
        self.location = location
        self.message = message
        self.hypothesis_id = hypothesis_id
        self.extra = extra or {}
        self._start = None

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed_ms = round((time.perf_counter() - self._start) * 1000, 2)
        data = {"elapsed_ms": elapsed_ms, **self.extra}
        if exc_type is not None:
            data["error"] = str(exc)
        _write_log(self.location, self.message, data, self.hypothesis_id)
        return False


def perf_log(location, message, data=None, hypothesis_id=None):
    _write_log(location, message, data or {}, hypothesis_id)


def _write_log(location, message, data, hypothesis_id):
    # #region agent log
    entry = {
        "sessionId": _SESSION_ID,
        "runId": _RUN_ID,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # #endregion
