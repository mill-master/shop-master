"""HTTP for the platform adapters: JSON in and out, paced per host, patient when throttled or cut off."""

import base64
import gzip
import json
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlsplit

# Seconds between two requests to one host. The platforms throttle bursts, and a gather sends dozens of requests.
GAP = 0.35
# Glovo throttles sooner than the others: at three requests a second it answered 429 in most gathers.
SLOWER = {"api.glovoapp.com": 1.0}
RETRY_ON = (429, 502, 503, 504)
ATTEMPTS = 4

_next_slot = {}
_lock = threading.Lock()


def _wait_turn(host):
    with _lock:
        now = time.monotonic()
        slot = max(now, _next_slot.get(host, 0.0))
        _next_slot[host] = slot + SLOWER.get(host, GAP)
    time.sleep(slot - now)


def _hold(host, seconds):
    """Keep every thread off `host` for a while: a throttled host is throttling all of them."""
    with _lock:
        _next_slot[host] = max(_next_slot.get(host, 0.0), time.monotonic() + seconds)


def _reply(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode(errors="replace")[:300]


def fetch(url, headers=None, body=None, form=None, timeout=40):
    """GET `url`, or POST `body` as JSON or `form` as a web form when one is given. Returns the decoded JSON reply.

    A failure is raised as RuntimeError naming the host and path, with the cause chained. For a refusal it also carries the answer: `status`, and `reply` with what the host said.
    """
    data = json.dumps(body).encode() if body is not None else urlencode(form).encode() if form is not None else None
    request = urllib.request.Request(url, data=data)
    request.add_header("accept", "application/json")
    request.add_header("accept-encoding", "gzip")
    if data is not None:
        request.add_header("content-type", "application/json" if body is not None else "application/x-www-form-urlencoded")
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
                refusal = RuntimeError(f"{call} answered {error.code}")
                answer = error.read() if error.fp else b""
                refusal.status, refusal.reply = error.code, _reply(gzip.decompress(answer) if answer[:2] == b"\x1f\x8b" else answer)
                raise refusal from error
            asked = error.headers.get("retry-after", "")
            # A throttled host stays shut for tens of seconds; shorter waits only spend the remaining attempts.
            _hold(host, float(asked) if asked.isdigit() else 4.0 * 3 ** attempt)
        except OSError as error:
            # No reply at all: a failed name lookup, a dropped connection, a timeout.
            if attempt == ATTEMPTS - 1:
                raise RuntimeError(f"{call} could not be reached ({getattr(error, 'reason', error)})") from error
            _hold(host, 2.0 * 2 ** attempt)


def lapses(token):
    """When a signed web token stops being valid, as seconds since the epoch; 0 when it does not say."""
    try:
        claims = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4))).get("exp", 0)
    except (IndexError, ValueError):
        return 0
