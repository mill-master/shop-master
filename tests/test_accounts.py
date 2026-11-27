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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import bolt  # noqa: E402
import glovo  # noqa: E402
import net  # noqa: E402
import wolt  # noqa: E402

loader = SourceFileLoader("shopmaster_accounts", str(ROOT / "bin" / "shopmaster"))
cli = module_from_spec(spec_from_loader(loader.name, loader))
loader.exec_module(cli)

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

    def test_a_valid_token_is_used_as_it_is(self):
        session = {"access_token": "good", "refresh_token": "r1", "expires_at": time.time() + 900}
        with mock.patch.object(wolt, "fetch", recording({}, [])):
            self.assertEqual(wolt.authorized(session)["authorization"], "Bearer good")


class WoltAccountPricing(unittest.TestCase):
    """The account is asked to price a finished basket and nothing else, and is left alone at the first pushback."""

    STORE = {"venue_id": "v", "currency": "GEL", "country": "GEO", "offer_ids": ["everyone"], "every_offer_id": ["everyone", "members"]}
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

    def test_a_refusal_rests_the_account_until_the_next_sign_in(self):
        account = self.account()
        replies = iter([refusal(403, {}), self.ROWS])
        self.price(account, lambda body: next(replies))
        self.assertIsNone(account["resting"]["until"])


class Glovo(unittest.TestCase):
    PLACE = {"cityCode": "TBI", "countryCode": "GE", "addressComponents": {"administrative_area_level_1": "Tbilisi"}}

    def sign_in(self, table, *typed):
        calls = []
        table = {"addresslookup": self.PLACE, "identity/v4/devices": {"urn": "glv:device:1"}, **table}
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
        table = {"addresslookup": self.PLACE, "oauth/refresh": {"accessToken": fresh, "refreshToken": "r2"}}
        with mock.patch.object(glovo, "fetch", recording(table, [])), mock.patch.dict(glovo._places, clear=True), \
                mock.patch.object(glovo, "ACCOUNT", account), mock.patch.object(glovo, "keep", lambda: kept.append(dict(account))):
            headers = glovo._headers(*POINT, True, account=True)
            visiting = glovo._headers(*POINT, True)
        self.assertEqual((headers["authorization"], headers["glovo-device-urn"]), (fresh, "glv:device:1"))
        self.assertEqual(kept[0]["refresh_token"], "r2")
        self.assertNotIn("authorization", visiting)  # shelves and stores are read without the account


class Bolt(unittest.TestCase):
    def sign_in(self, table, *typed):
        calls = []
        with mock.patch.object(bolt, "fetch", recording(table, calls)):
            return bolt.sign_in(answers(*typed), lambda text: None, *POINT), calls

    def ok(self, data):
        return {"code": 0, "message": "OK", "data": data}

    def test_the_texted_code_completes_the_sign_in(self):
        table = {"verification/start": self.ok({"state": "pending_phone_verification"}),
                 "verification/confirm": self.ok({"state": "complete", "auth": {"auth_username": "user-1"}})}
        session, calls = self.sign_in(table, "+995 555 12 34 56", " 4321 ")
        self.assertEqual((session["phone"], session["auth_username"]), ("+995555123456", "user-1"))
        self.assertEqual(calls[0][2]["phone_number"], "+995555123456")
        self.assertEqual({k: calls[1][2][k] for k in ("code", "type", "phone_uuid")}, {"code": "4321", "type": "phone", "phone_uuid": session["phone_uuid"]})

    def test_two_step_accounts_take_a_second_code_by_e_mail(self):
        states = iter([self.ok({"state": "pending_second_factor"}), self.ok({"state": "complete", "auth": {"auth_username": "user-1"}})])
        table = {"verification/start": self.ok({}), "verification/confirm": lambda body: next(states)}
        session, calls = self.sign_in(table, "+995555123456", "1111", "2222")
        self.assertEqual([(call[2].get("type"), call[2].get("code")) for call in calls], [("phone", None), ("phone", "1111"), ("email", None), ("email", "2222")])
        self.assertEqual(session["auth_username"], "user-1")

    def test_a_captcha_demand_and_an_unfinished_account_stop_with_the_reason(self):
        with self.assertRaisesRegex(RuntimeError, "asked for a captcha"):
            self.sign_in({"verification/start": {"code": 1, "message": "REQUIRED_BOT_CHALLENGE"}}, "+995555123456")
        table = {"verification/start": self.ok({}), "verification/confirm": self.ok({"state": "pending_signup"})}
        with self.assertRaisesRegex(RuntimeError, "pending_signup"):
            self.sign_in(table, "+995555123456", "1111")

    def test_the_lasting_credential_buys_a_refresh_token_and_that_an_access_token(self):
        session, calls, kept = {"auth_username": "user-1", "phone_uuid": "device-1"}, [], []
        fresh = token(900)
        table = {"auth/authenticate": self.ok({"refresh_token": "r1"}), "auth/getAccessTokenWithRotation": self.ok({"access_token": fresh, "refresh_token": "r2"})}
        with mock.patch.object(bolt, "fetch", recording(table, calls)), mock.patch.object(bolt, "keep", lambda: kept.append(dict(session))):
            headers = bolt.authorized(session)
        self.assertEqual(headers, {"authorization": f"Bearer {fresh}"})
        self.assertEqual(calls[0][1]["authorization"], "Basic " + base64.b64encode(b"user-1:device-1").decode())
        self.assertEqual(calls[1][1]["authorization"], "Bearer r1")
        self.assertEqual(session["refresh_token"], "r2")
        self.assertEqual(len(kept), 2)


class TokenFile(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        cli.ACCOUNTS_FILE = Path(folder.name) / "accounts.json"
        cli.POINT_FILE = Path(folder.name) / "point.json"
        cli.save(cli.POINT_FILE, {"lat": 41.69, "lon": 44.8, "label": "home"})

    def test_tokens_are_kept_for_the_owner_alone(self):
        cli.save_accounts({"wolt": {"refresh_token": "r"}})
        self.assertEqual(stat.S_IMODE(cli.ACCOUNTS_FILE.stat().st_mode), 0o600)
        self.assertEqual(cli.load_accounts(), {"wolt": {"refresh_token": "r"}})

    def test_the_account_report_names_who_is_signed_in_and_their_subscription(self):
        cli.save_accounts({"alpha": {"token": "t"}, "beta": {"token": "t"}})

        def unreadable(session, lat, lon):
            raise RuntimeError("beta.example.test/me answered 401")
        cli.PLATFORMS = {"alpha": SimpleNamespace(whoami=lambda session, lat, lon: {"who": "Nino", "member": True, "plan": "Alpha Plus"}),
                         "beta": SimpleNamespace(whoami=unreadable), "gamma": SimpleNamespace()}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.account(SimpleNamespace())
        self.assertEqual(out.getvalue().splitlines(), [
            "Alpha: signed in as Nino; Alpha Plus: yes",
            "Beta: signed in, but the account could not be read (beta.example.test/me answered 401)",
            "Gamma: not signed in"])


class Lapses(unittest.TestCase):
    def test_a_token_s_expiry_is_read_and_a_token_without_one_counts_as_lapsed(self):
        self.assertAlmostEqual(net.lapses(token(600)), time.time() + 600, delta=2)
        self.assertEqual(net.lapses("not-a-token"), 0)


if __name__ == "__main__":
    unittest.main()
