"""Bolt Food, read through the calls its own web client makes.

Bolt shows an anonymous visitor a store's delivery price and nothing else: its small-order, service and packaging fees appear after sign-in. A Bolt basket total built here is a lower bound.
"""

import base64
import time
from urllib.parse import urlencode
from uuid import uuid4

from net import fetch, lapses
from units import measure, money

HOST = "https://deliveryuser.live.boltsvc.net"
API = f"{HOST}/deliveryClient/public"
CLIENT = urlencode({
    "version": "FW.1.123.0", "language": "en-US", "deviceId": str(uuid4()),
    "deviceType": "web", "device_name": "web", "device_os_version": "web",
})
PREVIEW_BATCH = 20  # providers per preview request, as the web client sends them
PREVIEWED = 40      # search results looked into; Bolt ranks the relevant providers first

# The signed-in session, when there is one, and what to call after it changes so that it is kept. Both are set by the command-line tool.
ACCOUNT = None
keep = lambda: None  # noqa: E731


def call(method, body=None, **params):
    reply = fetch(f"{API}/{method}?{urlencode(params)}&{CLIENT}", body=body)
    if reply.get("code") != 0:
        raise RuntimeError(f"Bolt {method}: {reply.get('message')}")
    return reply["data"]


def _minor(lari):
    return round(lari * 100)


def discover(query, lat, lon, food):
    """Items matching `query`, provider by provider: Bolt's search names the stores (or, for `food`, the restaurants), and a second call previews what matched in each."""
    where = {"delivery_lat": lat, "delivery_lng": lon}
    tab = "restaurants" if food else "stores"
    providers = call("deliverySearch", {**where, "search_string": query, "filters": [], "search_tab_id": tab})["providers"][:PREVIEWED]
    hits = []
    for start in range(0, len(providers), PREVIEW_BATCH):
        batch = providers[start:start + PREVIEW_BATCH]
        previews = call("getProviderPreviewMenuItems", {
            **where, "provider_ids": [provider["id"] for provider in batch], "search_string": query, "purpose": "search",
        })["preview_items"]
        for provider in batch:
            items = (previews.get(str(provider["id"])) or {}).get("items") or {}
            for item in items.values():
                hits.append({
                    "store": str(provider["id"]),
                    "name": provider["name"].strip(),
                    "open": provider["availability"]["delivery"]["instant"],
                    "price": _minor(item["price"]["value"]),
                })
    return hits


def shelf(store, query, lat, lon, limit=8):
    """The best matches for `query` in one provider's menu, by Bolt's own relevance score."""
    items = call("searchInMenu", provider_id=store["key"], search_string=query, delivery_lat=lat, delivery_lng=lon)["items"]
    items = items if isinstance(items, dict) else {str(item["id"]): item for item in items}
    dishes = [item for item in items.values() if item.get("type") == "dish" and item.get("availability") == "in_stock"]
    dishes.sort(key=lambda dish: -(dish.get("score") or 0))
    offers = []
    for dish in dishes[:limit]:
        # A dish with choices to make shows a base price, sometimes a token one; the cheapest obligatory choices are added to it.
        name, price = dish["name"]["value"].strip(), _minor(dish["price"]["value"]) + _required_choices(dish, items)
        # Bolt prices the pack as named and, for goods it reckons by weight, adds the price per kilogram ("67,00 ₾/kg"); the two give the pack's weight.
        # Without that figure a product reckoned by weight has no size that can be trusted.
        per_kilo = ((dish.get("unit_price") or {}).get("unit_price") or {}).get("value") or ""
        by_weight = dish.get("selling_unit") == "kg"
        offers.append({
            "id": str(dish["id"]),
            "name": name,
            "price": price,
            "list": price,
            "size": [round(price / money(per_kilo) * 1000), "g"] if per_kilo.endswith("/kg") and money(per_kilo) else None if by_weight else measure(name),
            "from": dish.get("option_group_presence") not in (None, "none"),
            "stock": dish.get("available_quantity"),
            "limit": dish.get("order_limit_quantity"),
            "note": ((dish.get("description") or {}).get("value") or "").strip() or None,
        })
    return offers


def _required_choices(dish, items):
    """What the cheapest obligatory choices add to a dish's price. Its groups of choices and their options come in the same reply; each option is taken once."""
    added = 0
    for group in (items.get(str(child)) or {} for child in dish.get("child_ids") or []):
        options = [items.get(str(option)) or {} for option in group.get("child_ids") or []]
        prices = sorted(_minor((option.get("price") or {}).get("value") or 0) for option in options if option.get("availability", "in_stock") == "in_stock")
        added += sum(prices[: group.get("min") or 0])
    return added


def store(key, lat, lon):
    """One provider as it stands for this delivery point."""
    provider = call("getProviderOverview", {"provider_id": int(key), "delivery_lat": lat, "delivery_lng": lon})["provider"]
    delivery = provider["delivery"]
    eta = (provider.get("eta") or {}).get("delivery")
    notes = []
    if delivery.get("fee_range"):
        notes.append("Bolt gives a range for the delivery price here, so it varies with the order")
    return {
        "name": provider["name"].strip(),
        "url": f"https://food.bolt.eu/en-US/{provider['city_id']}/p/{provider['slug']}",
        "currency": delivery["fee"]["currency"].upper(),
        "open": provider["availability"]["delivery"]["instant"],
        "opens": (provider.get("overlay") or {}).get("text"),
        "eta": f"{eta['min'] // 60}-{eta['max'] // 60} min" if eta else None,
        "distance": (provider.get("distance") or {}).get("text"),
        "rating": (provider.get("rating") or {}).get("rating_value"),
        "fees": [{"label": "Delivery", "segments": [[0, None, _minor(delivery["fee"]["value"]), 0]]}],
        "caveat": "delivery price only: Bolt shows its service, small-order and packaging fees after sign-in, so the real total is higher",
        "partial": True,
        "notes": notes,
    }


# --- the shopper's own account ------------------------------------------------

def _account(path, body=None, headers=None, **params):
    """One call to Bolt's account service, which answers like the rest: a code, a message and the data."""
    reply = fetch(f"{HOST}/{path}?{urlencode(params)}&{CLIENT}", headers, body, acting=True)
    if reply.get("code") != 0:
        raise RuntimeError(f"Bolt {path}: {reply.get('message')}")
    return reply["data"]


def sign_in(ask, tell, lat, lon):
    """Sign in with the phone number and the code Bolt texts to it."""
    session = {"phone_uuid": str(uuid4()), "phone": ask("Phone number of your Bolt account with its country code, starting with +: ").replace(" ", "")}
    step = {"phone_uuid": session["phone_uuid"], "last_known_state": {}}
    try:
        _account("profile/verification/start", {**step, "type": "phone", "phone_number": session["phone"], "method": "sms"})
    except RuntimeError as refusal:
        if "REQUIRED_BOT_CHALLENGE" in str(refusal):
            raise RuntimeError("Bolt asked for a captcha before texting the code, which this tool does not solve.") from refusal
        raise
    done = _account("profile/verification/confirm", {**step, "type": "phone", "phone_number": session["phone"], "code": ask("Code from Bolt's SMS: ").strip()})
    if done["state"] == "pending_second_factor":
        # The account has two-step verification: Bolt e-mails a second code.
        _account("profile/verification/start", {**step, "type": "email"})
        done = _account("profile/verification/confirm", {**step, "type": "email", "phone_number": session["phone"], "code": ask("Bolt e-mailed a second code. Code: ").strip()})
    if done["state"] != "complete":
        raise RuntimeError(f"Bolt left the sign-in at \"{done['state']}\": that number has no finished Bolt account, and this tool does not create one.")
    session.update(auth_username=done["auth"]["auth_username"], refresh_token=done["auth"].get("refresh_token"), access_token=done["auth"].get("access_token"))
    return session


def authorized(session):
    """The header that acts for the signed-in account, with its access token renewed when it is about to lapse."""
    if not session.get("refresh_token"):
        # The lasting credential is the account's name with the device id it signed in from; it buys a refresh token.
        basic = base64.b64encode(f"{session['auth_username']}:{session['phone_uuid']}".encode()).decode()
        session["refresh_token"] = _account("profile/eater/auth/authenticate", {}, {"authorization": f"Basic {basic}"})["refresh_token"]
        keep()
    if lapses(session.get("access_token") or "") - time.time() < 60:
        renewed = _account("profile/eater/auth/getAccessTokenWithRotation", {}, {"authorization": f"Bearer {session['refresh_token']}"})
        session.update(access_token=renewed["access_token"], refresh_token=renewed.get("refresh_token") or session["refresh_token"])
        keep()
    return {"authorization": f"Bearer {session['access_token']}"}


def whoami(session, lat, lon):
    """Who is signed in, and whether they seem to hold Bolt Plus: the client shows a badge for subscribers, and that badge is the sign read here."""
    plus = _account("subscription/webview", None, authorized(session), delivery_lat=lat, delivery_lng=lon)
    return {"who": session["phone"], "member": bool(plus.get("subscribed_icon_url")), "plan": "Bolt Plus"}
