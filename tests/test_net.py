import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import net  # noqa: E402


def reply(payload):
    """What urlopen hands back for a JSON body: a readable context manager with headers."""
    body = io.BytesIO(json.dumps(payload).encode())
    body.headers = {}
    return body


def http_error(code, headers=None):
    return urllib.error.HTTPError("https://example.test/", code, "", headers or {}, None)


class Fetch(unittest.TestCase):
    def fetch(self, *outcomes):
        """Call fetch with urlopen yielding `outcomes` in turn; returns (result or raised error, attempts, sleeps)."""
        queue, sleeps = list(outcomes), []

        def urlopen(request, timeout):
            outcome = queue.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return reply(outcome)

        with mock.patch.object(net.urllib.request, "urlopen", urlopen), \
                mock.patch.object(net.time, "sleep", sleeps.append), mock.patch.object(net, "GAP", 0):
            try:
                result = net.fetch("https://example.test/")
            except Exception as error:
                result = error
        return result, len(outcomes) - len(queue), [pause for pause in sleeps if pause > 0]

    def test_a_request_that_got_no_reply_is_tried_again(self):
        result, attempts, _ = self.fetch(urllib.error.URLError("name lookup failed"), ConnectionResetError(), {"ok": 1})
        self.assertEqual((result, attempts), ({"ok": 1}, 3))

    def test_it_gives_up_after_four_attempts(self):
        result, attempts, _ = self.fetch(*[urllib.error.URLError("down")] * 5)
        self.assertIsInstance(result, urllib.error.URLError)
        self.assertEqual(attempts, 4)

    def test_a_throttled_request_waits_as_long_as_the_server_asks(self):
        result, attempts, sleeps = self.fetch(http_error(429, {"retry-after": "7"}), {"ok": 1})
        self.assertEqual((result, attempts, sleeps), ({"ok": 1}, 2, [7.0]))

    def test_a_refusal_is_not_retried(self):
        result, attempts, _ = self.fetch(http_error(403), {"ok": 1})
        self.assertEqual((result.code, attempts), (403, 1))


if __name__ == "__main__":
    unittest.main()
