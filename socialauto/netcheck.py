"""Is this computer online? (Task 07: the site shows "Internet yo'q — kutyapman" instead of errors, the bot waits.)

A plain TCP connect to a few well-known HTTPS hosts; no data is sent. Cached for a short time.
"""

from __future__ import annotations

import socket
import threading
import time

HOSTS = (("api.telegram.org", 443), ("api.github.com", 443), ("1.1.1.1", 443))
_cache: dict[str, float | bool] = {"at": 0.0, "online": True}
_lock = threading.Lock()


def online(max_age: float = 20.0, timeout: float = 3.0) -> bool:
    with _lock:
        if time.time() - float(_cache["at"]) < max_age:
            return bool(_cache["online"])
    ok = False
    for host, port in HOSTS:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                ok = True
                break
        except OSError:
            continue
    with _lock:
        _cache.update(at=time.time(), online=ok)
    return ok


def wait_until_online(stop=None, every: float = 10.0, log=None) -> bool:
    """Block until online (True) or `stop` is set (False). Logs once, quietly."""
    told = False
    while True:
        if online(max_age=0):
            return True
        if not told and log:
            log.info("No internet: waiting quietly and retrying every %.0f s", every)
            told = True
        if stop is not None:
            if stop.wait(every):
                return False
        else:
            time.sleep(every)


__all__ = ["online", "wait_until_online"]
