"""HTTP for the platform adapters: JSON in and out, paced and counted per host across runs, patient when throttled or cut off."""

import base64
import gzip
import json
import os
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode, urlsplit

try:
    import fcntl
except ImportError:  # Windows has no file locks of this kind; there the pacing holds within one run
    fcntl = None

# Seconds between two requests to one host. One a second is well under what the platforms' own pages send while loading; at three a second Glovo answered 429 in most gathers.
GAP = 1.0
# A request made for a signed-in account keeps a wider berth, and is made once: the first throttle or refusal is taken as the answer.
ACCOUNT_GAP = 3.0
# The most one host is asked in an hour, and the most of that for a signed-in account. They are this tool's own restraint; no platform publishes a figure.
# One comparison asks a host some 60 to 100 times. Glovo began answering 429 to requests a second apart after a day in which it was asked several hundred times an hour.
HOURLY = 300
ACCOUNT_HOURLY = 40
RETRY_ON = (429, 502, 503, 504)
ATTEMPTS = 4
# Seconds a host is left alone once it has answered 429 to every attempt of one request. Trying on would add to the load it is refusing.
REST = 600
# What has been asked of each host and when it may next be asked. It is kept on disk so that runs one after another, or side by side, pace themselves as one.
PACE_FILE = Path.home() / ".cache" / "shop-master" / "pace.json"

_lock = threading.Lock()


@contextmanager
def _pace(host):
    """One host's pacing record, held against other threads and other runs while it is read and amended."""
    PACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _lock, os.fdopen(os.open(PACE_FILE, os.O_RDWR | os.O_CREAT, 0o600), "r+") as kept:
        if fcntl:
            fcntl.flock(kept, fcntl.LOCK_EX)
        try:
            record = json.loads(kept.read() or "{}")
        except ValueError:  # a run was stopped while writing it
            record = {}
        yield record.setdefault(host, {})
        kept.seek(0)
        kept.truncate()
        json.dump(record, kept)


def _throttled(host, until):
    refusal = RuntimeError(f"{host} is throttling and is left alone until {time.strftime('%H:%M', time.localtime(until))}")
    refusal.status, refusal.reply = 429, None
    return refusal


def _wait_turn(host, gap, acting=False):
    """Take the next free moment on `host` and wait for it. Refuses while the host is being left alone, and once it has been asked as often as this tool asks in an hour."""
    with _pace(host) as asked:
        now = time.time()
        if asked.get("resting", 0) > now:
            raise _throttled(host, asked["resting"])
        if "since" not in asked or now - asked["since"] >= 3600:
            asked.update(since=now, count=0, for_account=0)
        if asked["count"] >= HOURLY or (acting and asked["for_account"] >= ACCOUNT_HOURLY):
            whose, most = (" for your account", ACCOUNT_HOURLY) if asked["count"] < HOURLY else ("", HOURLY)
            again = time.strftime("%H:%M", time.localtime(asked["since"] + 3600))
            raise RuntimeError(f"{host} has been asked {most} times within the hour{whose}, the most this tool asks; it may be asked again from {again}")
        asked["count"] += 1
        asked["for_account"] += bool(acting)
        slot = max(now, asked.get("next", 0))
        asked["next"] = slot + gap
    time.sleep(slot - now)


def _hold(host, seconds):
    """Keep every thread and every run off `host` for a while: a throttled host is throttling all of them."""
    with _pace(host) as asked:
        asked["next"] = max(asked.get("next", 0), time.time() + seconds)


def _reply(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode(errors="replace")[:300]


def fetch(url, headers=None, body=None, form=None, timeout=40, acting=False, patient=True):
    """GET `url`, or POST `body` as JSON or `form` as a web form when one is given. Returns the decoded JSON reply.

    `acting` marks a request made for a signed-in account, or one that signs in: it is paced more widely and never repeated, so that a throttled or refused account is left alone and a code is never sent twice. A request that is not `patient` is likewise made once: its failure is itself the answer wanted.

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
    attempts = ATTEMPTS if patient and not acting else 1
    for attempt in range(attempts):
        _wait_turn(host, ACCOUNT_GAP if acting else GAP, acting)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                if response.headers.get("content-encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt == attempts - 1:
                with _pace(host) as asked:
                    asked["resting"] = time.time() + REST
                raise _throttled(host, time.time() + REST) from error
            if error.code not in RETRY_ON or attempt == attempts - 1:
                refusal = RuntimeError(f"{call} answered {error.code}")
                answer = error.read() if error.fp else b""
                refusal.status, refusal.reply = error.code, _reply(gzip.decompress(answer) if answer[:2] == b"\x1f\x8b" else answer)
                raise refusal from error
            asked = error.headers.get("retry-after", "")
            # A throttled host stays shut for tens of seconds; shorter waits only spend the remaining attempts.
            _hold(host, float(asked) if asked.isdigit() else 4.0 * 3 ** attempt)
        except OSError as error:
            # No reply at all: a failed name lookup, a dropped connection, a timeout.
            if attempt == attempts - 1:
                raise RuntimeError(f"{call} could not be reached ({getattr(error, 'reason', error)})") from error
            _hold(host, 2.0 * 2 ** attempt)


def lapses(token):
    """When a signed web token stops being valid, as seconds since the epoch; 0 when it does not say."""
    try:
        claims = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4))).get("exp", 0)
    except (IndexError, ValueError):
        return 0
