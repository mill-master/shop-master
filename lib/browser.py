"""A browser window for signing in where a platform's own page is the only way through, and the reading of the session it leaves.

The shopper signs in by hand in an ordinary window, on a profile made for the occasion. The session is then read out of that profile with the browser run without a window, which fetches nothing from any site.
"""

import base64
import fcntl
import json
import os
import select
import shutil
import signal
import subprocess
from contextlib import contextmanager

NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
# Both launches keep the profile's cookies under the browser's built-in key, so that the windowless one reads what the window wrote without asking the desktop's keyring.
COMMON = ("--no-first-run", "--no-default-browser-check", "--password-store=basic")
PATIENCE = 30  # seconds the windowless browser is given to answer


def find():
    for name in NAMES:
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError("Signing in through a browser needs Google Chrome or Chromium, and neither was found.")


def window(profile, url):
    """Open `url` in a window on `profile`, and return when the shopper has closed the browser."""
    subprocess.run([find(), f"--user-data-dir={profile}", *COMMON, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


@contextmanager
def windowless(profile):
    """The browser run on `profile` without a window, as a function that sends one command of its debugging protocol and returns the result.

    The browser takes commands on its descriptor 3 and answers on 4, each message ending in a zero byte.
    """
    binary = find()
    commands, ours_out = os.pipe()
    ours_in, answers = os.pipe()
    # Copies numbered well above 4, so that handing them to the browser as 3 and 4 cannot overwrite one with the other.
    commands, answers = (fcntl.fcntl(end, fcntl.F_DUPFD_CLOEXEC, 10) for end in (commands, answers))
    browser = os.posix_spawn(
        binary, [binary, "--headless=new", "--remote-debugging-pipe", "--disable-background-networking", f"--user-data-dir={profile}", *COMMON, "about:blank"],
        os.environ, file_actions=[(os.POSIX_SPAWN_DUP2, commands, 3), (os.POSIX_SPAWN_DUP2, answers, 4),
                                  (os.POSIX_SPAWN_OPEN, 1, os.devnull, os.O_WRONLY, 0), (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0)])
    os.close(commands)
    os.close(answers)
    unread, sent = b"", 0

    def answer():
        nonlocal unread
        while b"\0" not in unread:
            if not select.select([ours_in], [], [], PATIENCE)[0]:
                raise RuntimeError("the browser did not answer")
            more = os.read(ours_in, 1 << 16)
            if not more:
                raise RuntimeError("the browser closed without answering; if its sign-in window is still open, close that first")
            unread += more
        message, _, unread = unread.partition(b"\0")
        return json.loads(message)

    def send(method, session, params):
        nonlocal sent
        sent += 1
        os.write(ours_out, json.dumps({"id": sent, "method": method, "params": params, **({"sessionId": session} if session else {})}).encode() + b"\0")
        return sent

    def ask(method, session=None, **params):
        awaited = send(method, session, params)
        while True:
            message = answer()
            if message.get("method") == "Fetch.requestPaused":
                # A page here fetches nothing: whatever it asks for is answered on the spot with an empty page, which still counts as the site's own.
                send("Fetch.fulfillRequest", message.get("sessionId"), {"requestId": message["params"]["requestId"], "responseCode": 200, "body": base64.b64encode(b"").decode(),
                                                                         "responseHeaders": [{"name": "content-type", "value": "text/html"}]})
            elif message.get("id") == awaited:
                if "error" in message:
                    raise RuntimeError(f"the browser refused {method}: {message['error'].get('message')}")
                return message["result"]

    try:
        yield ask
        ask("Browser.close")
    except BaseException:
        try:
            os.kill(browser, signal.SIGTERM)
        except ProcessLookupError:
            pass
        raise
    finally:
        os.close(ours_out)
        os.close(ours_in)
        os.waitpid(browser, 0)


def at(ask, site):
    """A page that counts as `site`'s own with nothing fetched from it. Returns the page's session."""
    page = ask("Target.attachToTarget", targetId=ask("Target.createTarget", url="about:blank")["targetId"], flatten=True)["sessionId"]
    ask("Fetch.enable", page, patterns=[{"urlPattern": "*"}])
    ask("Network.enable", page)
    ask("Network.setBypassServiceWorker", page, bypass=True)  # a site's worker kept in the profile would fetch the page itself
    ask("Page.navigate", page, url=f"https://{site}/")
    return page


def read(profile, site):
    """What `site` left in `profile`: its cookies as {name: value}, and the local storage of its pages as {key: value}."""
    with windowless(profile) as ask:
        cookies = {cookie["name"]: cookie["value"] for cookie in ask("Storage.getCookies")["cookies"]
                   if cookie["domain"].lstrip(".") == site or cookie["domain"].endswith(f".{site}")}
        kept = ask("Runtime.evaluate", at(ask, site), expression="JSON.stringify(Object.assign({}, localStorage))", returnByValue=True)["result"]["value"]
    return cookies, json.loads(kept)
