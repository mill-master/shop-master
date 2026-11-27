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

_next_slot = {}
_lock = threading.Lock()


def _wait_turn(host):
    with _lock:
        now = time.monotonic()
        slot = max(now, _next_slot.get(host, 0.0))
        _next_slot[host] = slot + GAP
    time.sleep(slot - now)


def fetch(url, headers=None, body=None, timeout=40):
    """GET `url`, or POST `body` as JSON when one is given. Returns the decoded JSON reply."""
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data)
    request.add_header("accept", "application/json")
    request.add_header("accept-encoding", "gzip")
    if data is not None:
        request.add_header("content-type", "application/json")
    for name, value in (headers or {}).items():
        request.add_header(name, value)

    host = urlsplit(url).netloc
    for attempt in range(4):
        _wait_turn(host)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                if response.headers.get("content-encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_ON or attempt == 3:
                raise
            asked = error.headers.get("retry-after", "")
            time.sleep(float(asked) if asked.isdigit() else 2.0 * 2 ** attempt)
        except OSError:
            # No reply at all: a failed name lookup, a dropped connection, a timeout.
            if attempt == 3:
                raise
            time.sleep(2.0 * 2 ** attempt)
