"""Refresh the stateless API client once per source revision, across sessions."""
import importlib
from pathlib import Path
import threading

_LOCK = threading.RLock()
_REFRESHED = {}


def refresh_client(module, *, importer=importlib):
    with _LOCK:
        source = Path(module.__file__).resolve()
        stat = source.stat()
        token = (id(module), stat.st_mtime_ns, stat.st_size)
        if _REFRESHED.get(module.__name__) != token:
            module = importer.reload(module)
            _REFRESHED[module.__name__] = (
                id(module), stat.st_mtime_ns, stat.st_size
            )
        return module
