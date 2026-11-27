"""Signing in, as each platform's web client does it. The replies are shaped as that client's code expects them; none of these routes has yet been walked with a real account."""

import base64
import contextlib
import io
import json
import stat
import sys
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import bolt  # noqa: E402
import glovo  # noqa: E402
import net  # noqa: E402
import wolt  # noqa: E402

loader = SourceFileLoader("shopmaster_accounts", str(ROOT / "bin" / "shopmaster"))
cli = module_from_spec(spec_from_loader(loader.name, loader))
loader.exec_module(cli)
# No case reads or writes the sign-ins really kept on the computer: a case that needs sign-ins points this at a folder of its own.
cli.ACCOUNTS_FILE = Path("/nonexistent/shop-master/accounts.json")

POINT = (41.6938, 44.8015)


def token(lapses_in):
    """A signed web token whose only meaningful part is when it lapses."""
    claims = base64.urlsafe_b64encode(json.dumps({"exp": time.time() + lapses_in}).encode()).decode().rstrip("=")
    return f"header.{claims}.signature"


def answers(*replies):
    queue = list(replies)
    return lambda prompt, secret=False: queue.pop(0)


def refusal(status, reply):
    error = RuntimeError(f"host/path answered {status}")
    error.status, error.reply = status, reply
    return error


def recording(table, calls):
    """A stand-in for fetch that notes each call and answers from `table`; an exception in the table is raised."""
    def fetch(url, headers=None, body=None, form=None, timeout=40, acting=False):
        calls.append((url, headers or {}, body if body is not None else form))
        for part, reply in table.items():
            if part in url:
                reply = reply(body if body is not None else form) if callable(reply) else reply
                if isinstance(reply, Exception):
                    raise reply
                return reply
        raise AssertionError(f"unexpected call to {url}")
    return fetch


class Wolt(unittest.TestCase):
    TOKENS = {"access_token": "access", "refresh_token": "refresh", "expires_in": 1800}

    def test_the_e_mailed_link_is_redeemed_for_tokens(self):
        calls = []
        with mock.patch.object(wolt, "fetch", recording({"wauth2/access_token": self.TOKENS}, calls)):
            session = wolt.sign_in(answers("", "https://wolt.com/en/me/magic_login?token=abc&ref=x"), lambda text: None, *POINT)
        self.assertEqual((session["access_token"], session["refresh_token"]), ("access", "refresh"))
        self.assertEqual(calls[0][2], {"grant_type": "email_login", "token": "abc", "audience": "wolt-com", "capabilities": "access_confirmation"})

    def test_a_texted_code_signs_in_when_wolt_asks_for_no_captcha(self):
        calls = []
        table = {"captcha/site_key": {"site_key": None, "operation_token": "op-1"}, "start-phone-number-authentication": {}, "wauth2/access_token": self.TOKENS}
        with mock.patch.object(wolt, "fetch", recording(table, calls)):
            session = wolt.sign_in(answers("+995 555 12 34 56", " 9876 "), lambda text: None, *POINT)
        self.assertEqual(session["refresh_token"], "refresh")
        self.assertEqual(calls[1][2], {"phone_number": "+995555123456", "message_delivery_method": "sms", "operation_token": "op-1"})
        self.assertEqual(calls[2][2], {"grant_type": "phone_number_otp", "phone_number": "+995555123456", "otp": "9876", "tenant": "wolt",
                                       "audience": "wolt-com", "capabilities": "access_confirmation"})

    def test_a_captcha_demand_on_the_phone_route_points_to_the_e_mailed_link(self):
        calls = []
        with mock.patch.object(wolt, "fetch", recording({"captcha/site_key": {"site_key": "key", "operation_token": "op-1"}}, calls)):
            with self.assertRaisesRegex(RuntimeError, "press Enter at the phone number"):
                wolt.sign_in(answers("+995555123456"), lambda text: None, *POINT)
        self.assertEqual(len(calls), 1)

    def test_a_spent_link_is_explained(self):
        with mock.patch.object(wolt, "fetch", recording({"wauth2/access_token": refusal(401, {"error_code": 126})}, [])):
            with self.assertRaisesRegex(RuntimeError, "expired or was already opened"):
                wolt.sign_in(answers("", "https://wolt.com/en/me/magic_login?token=abc"), lambda text: None, *POINT)

    def test_a_sign_in_wolt_wants_confirmed_goes_through_the_e_mailed_code(self):
        calls = []
        table = {
            "wauth2/access_token": lambda form: self.TOKENS if form["grant_type"] == "access_confirmation_token"
            else refusal(401, {"error_code": 130, "access_confirmation_token": "confirm-me"}),
            "access_confirmation/email/submit": {}, "access_confirmation/email": {},
        }
        with mock.patch.object(wolt, "fetch", recording(table, calls)):
            session = wolt.sign_in(answers("", "https://wolt.com/en/me/magic_login?token=abc", " 123456 "), lambda text: None, *POINT)
        self.assertEqual(session["refresh_token"], "refresh")
        self.assertEqual([call[2] for call in calls[1:3]], [{}, {"code": "123456"}])
        self.assertEqual(calls[1][1]["authorization"], "Bearer confirm-me")

    def test_a_lapsing_token_is_renewed_and_the_new_refresh_token_kept_at_once(self):
        session, kept = {"access_token": "old", "refresh_token": "r1", "expires_at": time.time() + 30}, []
        renewed = {"access_token": "new", "refresh_token": "r2", "expires_in": 1800}
        with mock.patch.object(wolt, "fetch", recording({"wauth2/access_token": renewed}, [])), \
                mock.patch.object(wolt, "keep", lambda: kept.append(dict(session))):
            headers = wolt.authorized(session)
        self.assertEqual(headers["authorization"], "Bearer new")
        self.assertEqual(kept[0]["refresh_token"], "r2")

    def test_a_renewal_that_hands_over_no_access_token_keeps_the_new_refresh_token_and_says_so(self):
        session, kept = {"access_token": "old", "refresh_token": "r1", "expires_at": 0}, []
        with mock.patch.object(wolt, "fetch", recording({"wauth2/access_token": {"refresh_token": "r2"}}, [])), \
                mock.patch.object(wolt, "keep", lambda: kept.append(dict(session))), self.assertRaisesRegex(RuntimeError, "renewed the sign-in with a reply this tool does not know"):
            wolt.authorized(session)
        self.assertEqual(kept[-1]["refresh_token"], "r2")

    def test_a_sign_in_answered_without_tokens_stops_in_plain_words(self):
        with mock.patch.object(wolt, "fetch", recording({"wauth2/access_token": {"status": "ok"}}, [])), \
                self.assertRaisesRegex(RuntimeError, "without the tokens this tool expects"):
            wolt.sign_in(answers("", "https://wolt.com/en/me/magic_login?token=abc"), lambda text: None, *POINT)

    def test_a_valid_token_is_used_as_it_is(self):
        session = {"access_token": "good", "refresh_token": "r1", "expires_at": time.time() + 900}
        with mock.patch.object(wolt, "fetch", recording({}, [])):
            self.assertEqual(wolt.authorized(session)["authorization"], "Bearer good")

    def test_the_account_is_read_from_replies_shaped_as_a_real_one_s(self):
        # Shaped as a real account's replies of 2026-11-27: the dates of a subscription are moments in seconds, and an account keeps its lapsed subscriptions.
        def subscription(paid_until):
            return {"id": "s", "plan": {"id": "p", "country": "GEO", "currency": "GEL", "name": "Wolt+"}, "start_date": 1760000000, "end_date": None,
                    "next_payment_date": paid_until, "paid_until_date": paid_until, "payment_cycle": "monthly", "saved_money": 4210}
        me = {"user": {"name": {"first_name": "Nino", "last_name": "K"}, "country": "GEO", "email": "nino@example.test"}}
        session = {"access_token": "good", "refresh_token": "r1", "expires_at": time.time() + 900}
        for paid_until, member in ((time.time() + 86400, True), (time.time() - 86400, False)):
            table = {"user/me": me, "subscriptions-api": {"subscriptions": [subscription(1765000000), subscription(paid_until)], "promotions": [], "partnerships": None}}
            with self.subTest(member=member), mock.patch.object(wolt, "fetch", recording(table, [])):
                self.assertEqual(wolt.whoami(session, *POINT), {"who": "Nino K", "member": member, "plan": "Wolt+"})
        with mock.patch.object(wolt, "fetch", recording({"user/me": me, "subscriptions-api": {"subscriptions": [], "promotions": []}}, [])):
            self.assertEqual(wolt.whoami(session, *POINT)["member"], False)

    def test_the_session_wolt_s_site_leaves_in_a_browser_is_taken_from_its_two_cookies(self):
        # As Wolt's web client writes them: each value JSON, the access token inside an object, both encoded for a cookie.
        access = token(1800)
        cookies = {"__wtoken": quote(json.dumps({"accessToken": access, "expirationTime": 1795790000000})), "__wrtoken": quote(json.dumps("refresh-1")), "cwc-consents": "x"}
        session = wolt.from_browser(cookies, {})
        self.assertEqual((session["access_token"], session["refresh_token"]), (access, "refresh-1"))
        self.assertAlmostEqual(session["expires_at"], time.time() + 1800, delta=2)
        # Without the access token the session is still good: it counts as lapsed, and the first use renews it.
        self.assertEqual(wolt.from_browser({"__wrtoken": quote(json.dumps("refresh-1"))}, {}), {"refresh_token": "refresh-1", "access_token": "", "expires_at": 0})
        self.assertIsNone(wolt.from_browser({"cwc-consents": "x"}, {"anything": "1"}))


class WoltAccountPricing(unittest.TestCase):
    """The account is asked to price a finished basket and nothing else, and is left alone at the first throttle or refusal."""

    STORE = {"venue_id": "v", "currency": "GEL", "country": "GEO", "scale": 1, "offer_ids": ["everyone"], "every_offer_id": ["everyone", "members"]}
    ROWS = {"checkout_rows": [{"template": "amount_row", "label": "Item subtotal", "amount": {"amount": 500}}]}
    LINES = [({"id": "milk", "base": 500, "price": 500}, 1)]

    def price(self, account, reply):
        calls, kept = [], []
        with mock.patch.object(wolt, "fetch", recording({"pages/checkout": reply}, calls)), mock.patch.object(wolt, "ACCOUNT", account), \
                mock.patch.object(wolt, "keep", lambda: kept.append(1)):
            return wolt.quote(self.STORE, self.LINES, *POINT), calls, kept

    def account(self):
        return {"access_token": "good", "refresh_token": "r1", "expires_at": time.time() + 900}

    def test_signed_in_the_basket_is_priced_as_the_account_s_with_every_campaign_put_to_wolt(self):
        priced, calls, _ = self.price(self.account(), self.ROWS)
        self.assertTrue(priced["mine"])
        self.assertEqual(calls[0][1]["authorization"], "Bearer good")
        self.assertEqual(calls[0][2]["purchase_plan"]["use_promo_discount_ids"], ["everyone", "members"])

    def test_a_throttled_account_is_rested_and_the_basket_priced_as_a_visitor_s(self):
        account = self.account()
        replies = iter([refusal(429, {}), self.ROWS])
        priced, calls, kept = self.price(account, lambda body: next(replies))
        self.assertFalse(priced["mine"])
        self.assertIn("Wolt throttled a request made for your account", priced["note"])
        self.assertNotIn("authorization", calls[1][1])
        self.assertEqual(calls[1][2]["purchase_plan"]["use_promo_discount_ids"], ["everyone"])
        self.assertAlmostEqual(account["resting"]["until"], time.time() + 3600, delta=5)
        self.assertEqual(len(kept), 1)

    def test_a_resting_account_is_not_asked_and_wakes_when_its_rest_is_over(self):
        account = {**self.account(), "resting": {"until": time.time() + 600, "why": "Wolt throttled a request made for your account"}}
        priced, calls, _ = self.price(account, self.ROWS)
        self.assertEqual((priced["mine"], len(calls)), (False, 1))
        self.assertNotIn("authorization", calls[0][1])
        account["resting"]["until"] = time.time() - 1
        priced, calls, _ = self.price(account, self.ROWS)
        self.assertTrue(priced["mine"])
        self.assertNotIn("resting", account)

    def test_a_pricing_for_the_account_in_an_unknown_form_falls_back_to_a_visitor_s(self):
        replies = iter([{"rows_of_another_kind": []}, self.ROWS])
        priced, calls, _ = self.price(self.account(), lambda body: next(replies))
        self.assertEqual((priced["mine"], priced["goods"], len(calls)), (False, 500, 2))
        self.assertIn("in a form this tool does not read (KeyError: 'checkout_rows'), so it is priced as for any visitor", priced["note"])
        self.assertNotIn("authorization", calls[1][1])

    def test_a_refusal_rests_the_account_until_the_next_sign_in(self):
        account = self.account()
        replies = iter([refusal(403, {}), self.ROWS])
        self.price(account, lambda body: next(replies))
        self.assertIsNone(account["resting"]["until"])


class Glovo(unittest.TestCase):
    PLACE = {"cityCode": "TBI", "countryCode": "GE", "addressComponents": {"administrative_area_level_1": "Tbilisi"}}

    def sign_in(self, table, *typed):
        calls = []
        table = {"addresslookup": self.PLACE, "seo-content": {}, "identity/v4/devices": {"urn": "glv:device:1"}, **table}
        with mock.patch.object(glovo, "fetch", recording(table, calls)), mock.patch.dict(glovo._places, clear=True):
            return glovo.sign_in(answers(*typed), lambda text: None, *POINT), calls

    def test_e_mail_and_password_buy_tokens_for_a_registered_device(self):
        access = {"access": {"accessToken": "a", "refreshToken": "r", "expiresIn": 1200, "tokenType": "bearer"}}
        session, calls = self.sign_in({"/methods": {"data": {"authenticationMethods": ["PASSWORD", "GOOGLE"]}}, "oauth/token": access}, "me@example.test", "secret")
        self.assertEqual({k: session[k] for k in ("device_urn", "access_token", "refresh_token")}, {"device_urn": "glv:device:1", "access_token": "a", "refresh_token": "r"})
        url, headers, body = calls[-1]
        self.assertEqual(body, {"grantType": "password", "username": "me@example.test", "password": "secret"})
        self.assertEqual(headers["glovo-device-urn"], "glv:device:1")
        self.assertNotIn("authorization", headers)

    def test_the_ways_sign_in_can_stop_are_each_explained(self):
        cases = [
            ({"/methods": {"data": {"authenticationMethods": []}}}, "no account with that e-mail"),
            ({"/methods": {"data": {"authenticationMethods": ["GOOGLE"]}}}, "has no password"),
            ({"/methods": {"data": {"authenticationMethods": ["PASSWORD"]}}, "oauth/token": refusal(401, {})}, "did not accept that password"),
            ({"/methods": {"data": {"authenticationMethods": ["PASSWORD"]}}, "oauth/token": {"twoFactor": {"twoFactorToken": "t"}}}, "second step"),
        ]
        for table, said in cases:
            with self.subTest(said=said), self.assertRaisesRegex(RuntimeError, said):
                self.sign_in(table, "me@example.test", "secret")

    def test_signed_in_requests_carry_the_device_and_a_bare_token_renewed_when_lapsing(self):
        account, kept = {"device_urn": "glv:device:1", "access_token": token(20), "refresh_token": "r1"}, []
        fresh = token(1200)
        table = {"addresslookup": self.PLACE, "seo-content": {}, "oauth/refresh": {"accessToken": fresh, "refreshToken": "r2"}}
        with mock.patch.object(glovo, "fetch", recording(table, [])), mock.patch.dict(glovo._places, clear=True), \
                mock.patch.object(glovo, "ACCOUNT", account), mock.patch.object(glovo, "keep", lambda: kept.append(dict(account))):
            headers = glovo._headers(*POINT, True, account=True)
            visiting = glovo._headers(*POINT, True)
        self.assertEqual((headers["authorization"], headers["glovo-device-urn"]), (fresh, "glv:device:1"))
        self.assertEqual(kept[0]["refresh_token"], "r2")
        self.assertNotIn("authorization", visiting)  # shelves and stores are read without the account

    def test_a_renewal_may_leave_the_refresh_token_standing_and_one_without_an_access_token_is_said(self):
        fresh = token(1200)
        for reply, kept_refresh, fails in (({"accessToken": fresh}, "r1", False), ({"access": {"accessToken": fresh, "refreshToken": "r2"}}, "r2", False), ({"refreshToken": "r3"}, "r3", True)):
            account = {"device_urn": "glv:device:1", "access_token": token(20), "refresh_token": "r1"}
            table = {"addresslookup": self.PLACE, "seo-content": {}, "oauth/refresh": reply}
            with self.subTest(reply=sorted(reply)), mock.patch.object(glovo, "fetch", recording(table, [])), mock.patch.dict(glovo._places, clear=True), \
                    mock.patch.object(glovo, "ACCOUNT", account), mock.patch.object(glovo, "keep", lambda: None):
                if fails:
                    with self.assertRaisesRegex(RuntimeError, "renewed the sign-in with a reply this tool does not know"):
                        glovo._headers(*POINT, True, account=True)
                else:
                    self.assertEqual(glovo._headers(*POINT, True, account=True)["authorization"], fresh)
                self.assertEqual(account["refresh_token"], kept_refresh)

    def test_the_session_glovo_s_site_leaves_is_its_stored_refresh_token_and_device(self):
        # As Glovo's web client writes them: the refresh token and the device in local storage as JSON, the access token in a cookie.
        storage = {"glovo_refresh_token": json.dumps("refresh-1"), "glv_device": json.dumps({"fingerprintsExpirationTime": 1795790000000, "urn": "glv:device:9"}), "glv_uuid": '"u"'}
        cookies = {"glovo_auth_info": quote(json.dumps({"accessToken": "aaa.bbb.ccc"}))}
        self.assertEqual(glovo.from_browser(cookies, storage), {"device_urn": "glv:device:9", "access_token": "aaa.bbb.ccc", "refresh_token": "refresh-1"})
        self.assertEqual(glovo.from_browser({}, storage)["access_token"], "")
        self.assertIsNone(glovo.from_browser(cookies, {"glv_device": storage["glv_device"]}))


class TokenFile(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        cli.ACCOUNTS_FILE = Path(folder.name) / "accounts.json"
        cli.POINT_FILE = Path(folder.name) / "point.json"
        cli.save(cli.POINT_FILE, {"lat": 41.69, "lon": 44.8, "label": "home"})

    def through_a_browser(self, platform, left):
        """Run `login PLATFORM --browser` with the browser stood in for. `left` is what the site left in it, as (cookies, storage). Returns (what was said, what the window saw)."""
        cli.BROWSER_PROFILE = cli.ACCOUNTS_FILE.parent / "browser"
        cli.PLATFORMS = {"wolt": wolt, "glovo": glovo, "bolt": bolt}
        seen, out = [], io.StringIO()
        with contextlib.ExitStack() as held:
            for module in cli.PLATFORMS.values():
                held.enter_context(mock.patch.object(module, "ACCOUNT", None, create=True))
            held.enter_context(mock.patch.object(cli.browser, "window", lambda profile, url: seen.append((url, stat.S_IMODE(profile.stat().st_mode)))))
            held.enter_context(mock.patch.object(cli.browser, "read", lambda profile, site: left))
            held.enter_context(mock.patch.object(cli, "describe_account", lambda platform, session, point: "(the account, described)"))
            held.enter_context(contextlib.redirect_stdout(out))
            try:
                cli.login(SimpleNamespace(platform=platform, browser=True))
            except SystemExit as stopped:
                return str(stopped), seen
        return out.getvalue(), seen

    def test_signing_in_through_a_browser_takes_over_the_session_and_discards_the_profile(self):
        said, seen = self.through_a_browser("wolt", ({"__wtoken": quote(json.dumps({"accessToken": "a.b.c"})), "__wrtoken": quote(json.dumps("refresh-1"))}, {}))
        self.assertEqual(seen, [("https://wolt.com/en/login", 0o700)])
        self.assertEqual(cli.load_accounts()["wolt"]["refresh_token"], "refresh-1")
        self.assertFalse(cli.BROWSER_PROFILE.exists())
        self.assertIn("then close the browser", said)
        self.assertIn("Signed in.", said)

    def test_a_browser_closed_without_a_session_signs_nothing_in(self):
        said, _ = self.through_a_browser("glovo", ({"other": "1"}, {}))
        self.assertEqual(said, "Not signed in. The browser was closed with no Glovo session in it.")
        self.assertEqual(cli.load_accounts(), {})
        self.assertFalse(cli.BROWSER_PROFILE.exists())

    def test_a_session_kept_in_an_unknown_form_is_refused_and_said(self):
        said, _ = self.through_a_browser("wolt", ({"__wrtoken": "not-json"}, {}))
        self.assertEqual(said, "Not signed in. Wolt's site kept its session in a form this tool does not know (JSONDecodeError), so nothing was taken from the browser.")
        self.assertFalse(cli.BROWSER_PROFILE.exists())

    def test_bolt_is_read_signed_out_only_and_says_why_without_asking_bolt_anything(self):
        asked = []
        for through_browser in (True, False):
            with mock.patch.object(bolt, "fetch", lambda *call, **more: asked.append(call)), mock.patch.object(cli, "PLATFORMS", {"bolt": bolt}), \
                    self.assertRaises(SystemExit) as stopped:
                cli.login(SimpleNamespace(platform="bolt", browser=through_browser))
            self.assertIn("Its fraud protection refused a sign-in from this tool on a real account", str(stopped.exception))
        self.assertEqual(asked, [])
        self.assertFalse(hasattr(bolt, "sign_in"))

    def test_a_sign_in_records_how_it_was_made(self):
        self.through_a_browser("wolt", ({"__wtoken": quote(json.dumps({"accessToken": "a.b.c"})), "__wrtoken": quote(json.dumps("refresh-1"))}, {}))
        self.assertEqual(cli.load_accounts()["wolt"]["via"], "a browser window")

    def with_wolt(self, table):
        """The real Wolt reader behind the tool's commands, answered from `table`, with what it holds put back afterwards."""
        held = contextlib.ExitStack()
        held.enter_context(mock.patch.object(cli, "PLATFORMS", {"wolt": wolt}))
        held.enter_context(mock.patch.object(wolt, "ACCOUNT", None))
        held.enter_context(mock.patch.object(wolt, "keep", wolt.keep))
        held.enter_context(mock.patch.object(wolt, "fetch", recording(table, [])))
        held.enter_context(contextlib.redirect_stdout(io.StringIO()))
        return held

    RENEWAL = {"wauth2/access_token": lambda form: {"access_token": token(1800), "refresh_token": "r2"}}

    def test_a_token_renewed_while_the_account_is_read_is_the_one_kept(self):
        # Wolt replaces the refresh token when it renews: the new one has to reach the file, or the sign-in is lost.
        cli.save_accounts({"wolt": {"access_token": "old", "refresh_token": "r1", "expires_at": 0}})
        me = {"user": {"name": {"first_name": "Nino"}, "country": "GEO"}}
        with self.with_wolt({**self.RENEWAL, "user/me": me, "subscriptions-api": {"subscriptions": []}}):
            cli.account(SimpleNamespace())
        self.assertEqual(cli.load_accounts()["wolt"]["refresh_token"], "r2")

    def test_a_token_renewed_while_signing_out_does_not_bring_the_sign_in_back(self):
        cli.save_accounts({"wolt": {"access_token": "old", "refresh_token": "r1", "expires_at": 0}, "glovo": {"refresh_token": "g1"}})
        with self.with_wolt({**self.RENEWAL, "wauth2/logout": {}}) as held:
            cli.logout(SimpleNamespace(platform="wolt"))
        self.assertEqual(cli.load_accounts(), {"glovo": {"refresh_token": "g1"}})

    def test_a_sign_in_step_answered_in_an_unknown_form_stops_in_plain_words(self):
        odd = {"captcha/site_key": {"site_key": None}}  # no operation token, which the next step needs
        with self.with_wolt(odd), mock.patch("builtins.input", lambda prompt: "+995555123456"), self.assertRaises(SystemExit) as stopped:
            cli.login(SimpleNamespace(platform="wolt", browser=False))
        self.assertEqual(str(stopped.exception), "Not signed in. Wolt answered a step of the sign-in in a form this tool does not know (KeyError: 'operation_token'). "
                                                 "Sign in through a browser window instead: login wolt --browser.")
        self.assertEqual(cli.load_accounts(), {})

    def test_tokens_are_kept_for_the_owner_alone(self):
        cli.save_accounts({"wolt": {"refresh_token": "r"}})
        self.assertEqual(stat.S_IMODE(cli.ACCOUNTS_FILE.stat().st_mode), 0o600)
        self.assertEqual(cli.load_accounts(), {"wolt": {"refresh_token": "r"}})

    def test_the_account_report_names_who_is_signed_in_and_their_subscription(self):
        cli.save_accounts({"alpha": {"token": "t"}, "beta": {"token": "t"}})

        def unreadable(session, lat, lon):
            raise RuntimeError("beta.example.test/me answered 401")
        cli.PLATFORMS = {"alpha": SimpleNamespace(whoami=lambda session, lat, lon: {"who": "Nino", "member": True, "plan": "Alpha Plus"}),
                         "beta": SimpleNamespace(whoami=unreadable), "gamma": SimpleNamespace(), "delta": SimpleNamespace(NO_SIGN_IN="Delta refuses.")}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.account(SimpleNamespace())
        self.assertEqual(out.getvalue().splitlines(), [
            "Alpha: signed in as Nino; Alpha Plus: yes",
            "Beta: signed in, but the account could not be read (beta.example.test/me answered 401)",
            "Gamma: not signed in",
            "Delta: read signed out only"])


class Lapses(unittest.TestCase):
    def test_a_token_s_expiry_is_read_and_a_token_without_one_counts_as_lapsed(self):
        self.assertAlmostEqual(net.lapses(token(600)), time.time() + 600, delta=2)
        self.assertEqual(net.lapses("not-a-token"), 0)


if __name__ == "__main__":
    unittest.main()
