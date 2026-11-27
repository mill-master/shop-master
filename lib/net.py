"""HTTP for the platform adapters: JSON in and out, paced per host, patient when throttled or cut off."""

import gzip
import json
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

# Seconds between two requests to one host. The platforms throttle bursts, and a gather sends dozens of requests; at 0.2 Glovo answered some with 429.
GAP = 0.35
RETRY_ON = (429, 502, 503, 504)
ATTEMPTS = 4

_next_slot = {}
_lock = threading.Lock()


def _wait_turn(host):
    with _lock:
        now = time.monotonic()
        slot = max(now, _next_slot.get(host, 0.0))
        _next_slot[host] = slot + GAP
    time.sleep(slot - now)


def _hold(host, seconds):
    """Keep every thread off `host` for a while: a throttled host is throttling all of them."""
    with _lock:
        _next_slot[host] = max(_next_slot.get(host, 0.0), time.monotonic() + seconds)


def fetch(url, headers=None, body=None, timeout=40):
    """GET `url`, or POST `body` as JSON when one is given. Returns the decoded JSON reply.

    A failure is raised as RuntimeError naming the host and path, with the cause chained.
    """
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data)
    request.add_header("accept", "application/json")
    request.add_header("accept-encoding", "gzip")
    if data is not None:
        request.add_header("content-type", "application/json")
    for name, value in (headers or {}).items():
        request.add_header(name, value)

    target = urlsplit(url)
    host, call = target.netloc, f"{target.netloc}{target.path}"
    for attempt in range(ATTEMPTS):
        _wait_turn(host)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                if response.headers.get("content-encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_ON or attempt == ATTEMPTS - 1:
                raise RuntimeError(f"{call} answered {error.code}") from error
            asked = error.headers.get("retry-after", "")
            # A throttled host stays shut for tens of seconds; shorter waits only spend the remaining attempts.
            _hold(host, float(asked) if asked.isdigit() else 4.0 * 3 ** attempt)
        except OSError as error:
            # No reply at all: a failed name lookup, a dropped connection, a timeout.
            if attempt == ATTEMPTS - 1:
                raise RuntimeError(f"{call} could not be reached ({getattr(error, 'reason', error)})") from error
            _hold(host, 2.0 * 2 ** attempt)
