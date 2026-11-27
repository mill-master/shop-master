"""The windowless browser, run for real where one is installed. Nothing is fetched: a page is answered inside the browser, so the test needs no network."""

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import browser  # noqa: E402


class Windowless(unittest.TestCase):
    @unittest.skipUnless(any(shutil.which(name) for name in browser.NAMES), "no Chrome or Chromium here")
    def test_what_a_site_left_in_a_profile_is_read_back_and_no_other_site_s(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        later = time.time() + 3600
        with browser.windowless(folder.name) as ask:
            ask("Storage.setCookies", cookies=[{"name": "session", "value": "kept", "domain": ".shop.example", "path": "/", "expires": later},
                                               {"name": "session", "value": "another site's", "domain": "elsewhere.example", "path": "/", "expires": later}])
            ask("Runtime.evaluate", browser.at(ask, "shop.example"), expression="localStorage.setItem('token', JSON.stringify('refresh-1'))")
        self.assertEqual(browser.read(folder.name, "shop.example"), ({"session": "kept"}, {"token": '"refresh-1"'}))

    def test_a_computer_without_a_browser_is_told_what_is_missing(self):
        with mock.patch.object(browser.shutil, "which", lambda name: None), self.assertRaisesRegex(RuntimeError, "needs Google Chrome or Chromium"):
            browser.find()


if __name__ == "__main__":
    unittest.main()
