import io
import json
import sys
import tempfile
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
    acting = False

    def setUp(self):
        # Each case keeps its pacing record in a folder of its own, so that every host starts free and the shopper's record is left alone.
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        kept = mock.patch.object(net, "PACE_FILE", Path(folder.name) / "pace.json")
        kept.start()
        self.addCleanup(kept.stop)

    def fetch(self, *outcomes):
        """Call fetch with urlopen yielding `outcomes` in turn; returns (result or raised error, attempts, sleeps)."""
        queue, sleeps = list(outcomes), []
        net.PACE_FILE.unlink(missing_ok=True)

        def urlopen(request, timeout):
            outcome = queue.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return reply(outcome)

        with mock.patch.object(net.urllib.request, "urlopen", urlopen), \
                mock.patch.object(net.time, "sleep", sleeps.append), mock.patch.object(net, "GAP", 0), mock.patch.object(net, "ACCOUNT_GAP", 0):
            try:
                result = net.fetch("https://example.test/", acting=self.acting)
            except Exception as error:
                result = error
        return result, len(outcomes) - len(queue), [pause for pause in sleeps if pause > 0]

    def test_a_request_that_got_no_reply_is_tried_again(self):
        result, attempts, _ = self.fetch(urllib.error.URLError("name lookup failed"), ConnectionResetError(), {"ok": 1})
        self.assertEqual((result, attempts), ({"ok": 1}, 3))

    def test_it_gives_up_after_four_attempts_and_names_the_call(self):
        result, attempts, _ = self.fetch(*[urllib.error.URLError("down")] * 5)
        self.assertEqual(str(result), "example.test/ could not be reached (down)")
        self.assertIsInstance(result.__cause__, urllib.error.URLError)
        self.assertEqual(attempts, 4)

    def test_a_throttled_host_is_left_alone_as_long_as_it_asks(self):
        result, attempts, sleeps = self.fetch(http_error(429, {"retry-after": "7"}), {"ok": 1})
        self.assertEqual((result, attempts, [round(pause) for pause in sleeps]), ({"ok": 1}, 2, [7]))

    def test_a_request_made_for_an_account_is_never_repeated(self):
        self.acting = True
        result, attempts, sleeps = self.fetch(http_error(429, {"retry-after": "7"}), {"ok": 1})
        self.assertRegex(str(result), r"^example.test is throttling and is left alone until \d\d:\d\d$")
        self.assertEqual((result.status, attempts, sleeps), (429, 1, []))
        result, attempts, _ = self.fetch(urllib.error.URLError("down"), {"ok": 1})
        self.assertEqual(attempts, 1)

    def test_requests_to_one_host_are_spaced_and_an_account_s_more_widely(self):
        waits = []
        with mock.patch.object(net.time, "sleep", waits.append), mock.patch.object(net.time, "time", lambda: 100.0):
            for gap in (net.GAP, net.GAP, net.ACCOUNT_GAP, net.GAP):
                net._wait_turn("example.test", gap)
        self.assertEqual(waits, [0.0, 1.0, 2.0, 5.0])

    def test_the_pacing_is_kept_on_disk_so_that_a_later_run_waits_its_turn_too(self):
        waits = []
        with mock.patch.object(net.time, "sleep", waits.append), mock.patch.object(net.time, "time", lambda: 100.0):
            net._wait_turn("example.test", net.GAP)
            net._hold("example.test", 30)
        self.assertEqual(json.loads(net.PACE_FILE.read_text())["example.test"], {"since": 100.0, "count": 1, "for_account": 0, "next": 130.0})
        with mock.patch.object(net.time, "sleep", waits.append), mock.patch.object(net.time, "time", lambda: 104.0):
            net._wait_turn("example.test", net.GAP)  # as a run started four seconds later would
            net._wait_turn("other.test", net.GAP)
        self.assertEqual(waits, [0.0, 26.0, 0.0])

    def test_a_host_is_asked_only_so_often_in_an_hour(self):
        clock = [100.0]
        with mock.patch.object(net.time, "sleep", lambda pause: None), mock.patch.object(net.time, "time", lambda: clock[0]), \
                mock.patch.object(net, "HOURLY", 3), mock.patch.object(net, "ACCOUNT_HOURLY", 1):
            net._wait_turn("example.test", 0, acting=True)
            with self.assertRaisesRegex(RuntimeError, r"example.test has been asked 1 times within the hour for your account, the most this tool asks; it may be asked again from \d\d:\d\d"):
                net._wait_turn("example.test", 0, acting=True)
            net._wait_turn("example.test", 0)
            net._wait_turn("example.test", 0)
            with self.assertRaisesRegex(RuntimeError, "example.test has been asked 3 times within the hour, the most this tool asks"):
                net._wait_turn("example.test", 0)
            clock[0] += 3600
            net._wait_turn("example.test", 0, acting=True)  # a new hour

    def test_a_refused_turn_stops_the_request_before_it_is_sent(self):
        with mock.patch.object(net, "HOURLY", 0):
            result, attempts, _ = self.fetch({"ok": 1})
        self.assertEqual((type(result), attempts), (RuntimeError, 0))

    def test_a_record_cut_short_by_a_stopped_run_is_started_again(self):
        net.PACE_FILE.write_text('{"example.test": {"since": 1')
        with mock.patch.object(net.time, "sleep", lambda pause: None):
            net._wait_turn("example.test", net.GAP)
        self.assertEqual(json.loads(net.PACE_FILE.read_text())["example.test"]["count"], 1)

    def test_a_host_that_throttles_every_attempt_is_left_alone_by_this_run_and_the_next(self):
        result, attempts, _ = self.fetch(*[http_error(429)] * 4, {"ok": 1})
        self.assertRegex(str(result), r"^example.test is throttling and is left alone until \d\d:\d\d$")
        self.assertEqual(attempts, 4)
        sent = []
        with mock.patch.object(net.urllib.request, "urlopen", lambda request, timeout: sent.append(request)), mock.patch.object(net.time, "sleep", lambda pause: None):
            for _ in range(3):  # as later lookups of this run, or a run started afterwards, would ask
                with self.assertRaisesRegex(RuntimeError, "is throttling and is left alone until"):
                    net.fetch("https://example.test/")
            self.assertEqual(sent, [])
            later = net.time.time() + net.REST + 1
            with mock.patch.object(net.time, "time", lambda: later), mock.patch.object(net.urllib.request, "urlopen", lambda request, timeout: reply({"ok": 1})):
                self.assertEqual(net.fetch("https://example.test/"), {"ok": 1})

    def test_a_reply_with_nothing_in_it_is_an_empty_answer_and_one_that_is_not_json_names_its_call(self):
        def answering(raw):
            body = io.BytesIO(raw)
            body.headers = {}
            return lambda request, timeout: body
        with mock.patch.object(net.time, "sleep", lambda pause: None):
            with mock.patch.object(net.urllib.request, "urlopen", answering(b"")):
                self.assertEqual(net.fetch("https://example.test/logout"), {})
            with mock.patch.object(net.urllib.request, "urlopen", answering(b"<html>busy</html>")), \
                    self.assertRaisesRegex(RuntimeError, r"^example.test/logout answered with something that is not JSON$"):
                net.fetch("https://example.test/logout")

    def test_a_request_whose_failure_is_the_answer_is_made_once(self):
        queue = [http_error(503), {"ok": 1}]

        def urlopen(request, timeout):
            raise queue.pop(0)
        with mock.patch.object(net.urllib.request, "urlopen", urlopen), mock.patch.object(net.time, "sleep", lambda pause: None), \
                self.assertRaisesRegex(RuntimeError, "answered 503"):
            net.fetch("https://example.test/", patient=False)
        self.assertEqual(len(queue), 1)

    def test_a_refusal_is_not_retried(self):
        result, attempts, _ = self.fetch(http_error(403), {"ok": 1})
        self.assertEqual((str(result), result.__cause__.code, attempts), ("example.test/ answered 403", 403, 1))


if __name__ == "__main__":
    unittest.main()
