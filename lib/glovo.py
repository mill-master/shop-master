"""Glovo, read through the calls its own web client makes.

Glovo prices a basket only for a signed-in customer. The service fee, the small-basket surcharge and a store's basket-wide offers are therefore built from the parameters it publishes with each store, and have not been checked against a priced order.
"""

import json
import re
import threading
import time
import unicodedata
from urllib.parse import quote as urlquote, unquote
from uuid import uuid4

from net import fetch, lapses
from units import measure, money

API = "https://api.glovoapp.com"
SITE = "glovoapp.com"
SIGN_IN_PAGE = "https://glovoapp.com/en/login"

# The header set of Glovo's web client; the API refuses requests that carry less of it.
STATIC = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en",
    "origin": "https://glovoapp.com",
    "referer": "https://glovoapp.com/",
    "glovo-api-version": "14",
    "glovo-app-context": "web",
    "glovo-app-development-state": "prod",
    "glovo-app-platform": "web",
    "glovo-app-type": "customer",
    "glovo-app-version": "v1.3024.0",
    "glovo-client-info": "web-customer-web-react/v1.3024.0 project:customer-web",
    "glovo-language-code": "en",
    "glovo-perseus-consent": "essential",
    "glovo-request-ttl": "7500",
    "glovo-delivery-location-accuracy": "0",
}
SESSION = str(uuid4())
CLIENT = str(uuid4())
STARTED = str(int(time.time() * 1000))

FOOD_CATEGORY = "1"  # Glovo's category number for restaurants
GROCERIES = "4"
ENOUGH_STORES = 3     # stores with products in a search, short of which the groceries are searched on their own; a run reads that many stores of a platform

# The signed-in session, when there is one, and what to call after it changes so that it is kept. Both are set by the command-line tool.
ACCOUNT = None
keep = lambda: None  # noqa: E731

_places = {}
_placing = threading.Lock()


def place(lat, lon):
    """Glovo's own reading of the delivery point: its city and country codes and the city's name. Refuses a point in a country Glovo is not in."""
    with _placing:  # searches start together, and the first to ask settles the point for all of them
        if (lat, lon) not in _places:
            found = fetch(f"{API}/v3/addresslookup/pub/coordinates?latitude={lat}&longitude={lon}&allowFallback=true", _headers(lat, lon))
            # Glovo names a city for any point on earth. Where it does not operate it has no page for the country and no server answers a search,
            # which a patient request would find out over a minute of retries for every search; the two together are taken as the answer.
            try:
                fetch(f"{API}/seo-content/locales/en/countries/{found['countryCode'].lower()}", _headers(lat, lon))
            except RuntimeError as no_page:
                if getattr(no_page, "status", None) == 404:
                    located = {**_headers(lat, lon), "glovo-location-city-code": found["cityCode"], "glovo-location-country-code": found["countryCode"]}
                    try:
                        fetch(f"{API}/v1/web/store_wall/search?searchQuery=a", located, {"searchContext": {"searchId": str(uuid4())}}, patient=False)
                    except RuntimeError as no_server:
                        found["absent"] = getattr(no_server, "status", None) == 503
            _places[lat, lon] = found
    if _places[lat, lon].get("absent"):
        raise RuntimeError(f"Glovo does not operate in {_places[lat, lon]['addressComponents'].get('country') or _places[lat, lon]['countryCode']}")
    return _places[lat, lon]


def _headers(lat, lon, located=False, account=False):
    headers = {
        **STATIC,
        "glovo-delivery-location-latitude": str(lat),
        "glovo-delivery-location-longitude": str(lon),
        "glovo-delivery-location-timestamp": str(int(time.time() * 1000)),
        "glovo-perseus-client-id": CLIENT,
        "glovo-perseus-session-id": SESSION,
        "glovo-perseus-session-timestamp": STARTED,
        "glovo-dynamic-session-id": SESSION,
        "glovo-request-id": str(uuid4()),
    }
    if located:
        found = place(lat, lon)
        headers["glovo-location-city-code"] = found["cityCode"]
        headers["glovo-location-country-code"] = found["countryCode"]
    if account and ACCOUNT:
        # Only what needs the account is asked in its name; shelves and stores are read as any visitor reads them.
        # Signed in, the web client names its registered device and sends the access token bare.
        if lapses(ACCOUNT["access_token"]) - time.time() < 60:
            renewed = fetch(f"{API}/oauth/refresh", {**headers, "glovo-device-urn": ACCOUNT["device_urn"]}, {"refreshToken": ACCOUNT["refresh_token"]}, acting=True)
            renewed = renewed.get("access", renewed)
            ACCOUNT.update(access_token=renewed["accessToken"], refresh_token=renewed["refreshToken"])
            keep()
        headers["glovo-device-urn"] = ACCOUNT["device_urn"]
        headers["authorization"] = ACCOUNT["access_token"]
    return headers


def _find(node, key):
    """The first object anywhere under `node` that has `key`."""
    if isinstance(node, dict):
        if key in node:
            return node
        node = list(node.values())
    if isinstance(node, list):
        for child in node:
            found = _find(child, key)
            if found:
                return found
    return None


def _minor(lari):
    return round(lari * 100)


def discover(query, lat, lon, food):
    """Products matching `query`, store by store (restaurant by restaurant for `food`). Glovo answers with its search screen: a card per store, followed by a row of that store's matching products.

    A search across every kind of store shows products only for the stores it ranks first, and for a word that is also a dish those are restaurants. When it shows products for few stores, the groceries are therefore searched on their own as well.
    """
    def search(category):
        reply = fetch(f"{API}/v1/web/store_wall/search?searchQuery={urlquote(query)}" + (f"&categoryId={category}" if category else ""),
                      _headers(lat, lon, True), {"searchContext": {"searchId": str(uuid4())}})
        return _cards(reply["data"]["body"]["data"]["elements"], food)
    if food:
        return search(FOOD_CATEGORY)
    hits = search(None)
    if len({hit["store"] for hit in hits}) < ENOUGH_STORES:
        hits += [hit for hit in search(GROCERIES) if hit not in hits]
    return hits


def _cards(elements, food):
    """The products on a search screen, each with the store whose card stands before its row."""
    hits, card = [], None
    for element in elements:
        kind = element.get("type")  # a screen with nothing found carries an element of no type
        if kind == "STORE_CARD_V2":
            state = _find(element, "shopIsOpen")  # the card's display event carries the store's state
            if not state:
                raise RuntimeError(f"Glovo's search card for {element['data'].get('slug')} came without the store's state")
            title = ((element["data"].get("title") or {}).get("text") or {}).get("text")
            card = {"store": element["data"]["slug"], "name": title or element["data"]["slug"], "open": state["shopIsOpen"] == "true"}
            if (state["glovoCategoryId"] == FOOD_CATEGORY) != food:
                card = None
        elif kind == "CAROUSEL" and card:
            for product in element["data"]["elements"]:
                shown = (product["data"].get("pricing") or {}).get("finalPrice")
                if shown:
                    hits.append({**card, "price": money(shown)})
            card = None
    return hits


def shelf(store, query, lat, lon, limit=8):
    """The best matches for `query` in one store."""
    reply = fetch(f"{API}/v3/stores/{store['store_id']}/addresses/{store['address_id']}/search?query={urlquote(query)}", _headers(lat, lon, True))
    offers = []
    for group in reply.get("results", []):
        for product in group.get("products", []):
            # A dish with choices to make shows its base price; the cheapest obligatory choices are added to it.
            added = sum(sum(sorted(_minor(choice.get("priceImpact") or 0) for choice in choices.get("attributes") or [])[: choices.get("min") or 0])
                        for choices in product.get("attributeGroups") or [])
            offer = {
                "id": str(product["id"]),
                "name": product["name"].strip(),
                "price": _minor(product["price"]) + added,
                "list": _minor(product["price"]) + added,
                # Glovo gives no size apart from the name, and does not mark goods sold by weight.
                "size": measure(product["name"]),
                "from": bool(product.get("attributeGroups")),
                "note": (product.get("description") or "").strip() or None,
            }
            promotion = product.get("promotion") or {}
            if promotion.get("price") and not promotion.get("isPrime"):
                offer["price"] = _minor(promotion["price"]) + added
            elif promotion:
                extra = f"offer: {promotion.get('title')}" + (" (Prime members)" if promotion.get("isPrime") else "")
                offer["note"] = f"{extra}. {offer['note']}" if offer["note"] else extra
            offers.append(offer)
            if len(offers) == limit:
                return offers
    return offers


def schedule(delivery, service, surcharges):
    """A store's fee rules as solver segments, from the numbers Glovo publishes with it.

    `service` holds a percentage of the basket with a lower and an upper bound. Each of `surcharges` is an extra charge on baskets inside a range; one marked CAPPED is read as the gap up to the range's end, no larger than the stated amount. Both readings come from the field names.
    """
    fees = [{"label": "Delivery", "segments": [[0, None, _minor(delivery), 0]]}]
    if service:
        rate, low, high = service["setupValue"] / 100, service["minValue"], service["maxValue"]
        segments = [[0, low / rate, low, 0], [low / rate, high / rate, 0, rate], [high / rate, None, high, 0]] if rate else [[0, None, low, 0]]
        fees.append({"label": "Service fee", "segments": segments})
    segments = []
    for band in surcharges:
        low, high, amount = _minor(band["lowerBound"]), _minor(band["upperBound"]), _minor(band["surchargeInfo"]["amount"])
        if band["surchargeStrategy"] == "CAPPED":
            segments += [[low, high - amount, amount, 0], [high - amount, high, high, -1]]
        else:
            segments.append([low, high, amount, 0])
    if segments:
        fees.append({"label": "Small order fee", "segments": segments})
    return fees


def store(key, lat, lon):
    """One store as it stands for this delivery point: state, fee rules, standing offers."""
    headers = _headers(lat, lon, True)
    info = fetch(f"{API}/v3/stores/{urlquote(key)}?includeClosed=true&includeDisabled=false", headers)
    surcharges = fetch(f"{API}/v1/stores/{info['id']}/addresses/{info['addressId']}/node/store_fees", headers)["data"]["ranges"]
    found = place(lat, lon)
    # The city as Glovo's page addresses spell it: "T'bilisi" is tbilisi, "Barcelona" barcelona. Under another name the store's page still opens, reduced.
    named = found["addressComponents"].get("locality") or found["cityCode"]
    plain = unicodedata.normalize("NFKD", named).encode("ascii", "ignore").decode().replace("'", "")
    city = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    fees = schedule(info["deliveryFeeInfo"]["fee"], info.get("serviceFeeInfo"), surcharges)
    notes = []
    for offer in info.get("promotions", []):
        least = offer.get("minimumBasketSizeCents") or 0
        text = " ".join(part for part in (offer["title"], offer.get("description")) if part) + (f", baskets from {least / 100:.2f}" if least else "")
        if offer.get("prime") and "prime" not in text.lower():
            text += " (Prime members)"
        # A percentage off the whole basket is the one kind that changes a total and is open to all; offers on single products show in their shelf prices.
        counted = offer["type"] == "BASKET_PERCENTAGE" and not offer.get("prime")
        if counted:
            fees.append({"label": f"Offer: {text}", "segments": [[least, None, 0, -offer["percentage"] / 100]]})
        notes.append(f"offer: {text}" + (" (counted in the totals)" if counted else ""))
    if info.get("primeAvailable"):
        notes.append("Glovo Prime applies at this store; a member pays less in fees than shown")
    return {
        "name": info["name"].strip(),
        "url": f"https://glovoapp.com/en/{found['countryCode'].lower()}/{city}/stores/{info['slug']}",
        "currency": surcharges[0]["upperBoundInfo"]["currencyCode"] if surcharges else None,
        "store_id": info["id"],
        "address_id": info["addressId"],
        "open": bool(info["open"]),
        "opens": info.get("closedStatusMessage") or (info.get("availability") or {}).get("footerLabel"),
        "eta": None,
        "distance": info.get("distance"),
        "rating": info.get("rating"),
        "fees": fees,
        "caveat": "fees and offers are computed from Glovo's published parameters, not priced by Glovo",
        "notes": notes,
    }


# --- the shopper's own account ------------------------------------------------

def from_browser(cookies, storage):
    """The session Glovo's site leaves in a browser signed in to it, or None when the browser holds none.

    The site keeps the refresh token and the device it registered in its local storage, each as JSON, and the access token in a cookie. With no access token the first request made for the account fetches one.
    """
    if not storage.get("glovo_refresh_token") or not storage.get("glv_device"):
        return None
    access = json.loads(unquote(cookies.get("glovo_auth_info") or "{}")).get("accessToken", "")
    return {"device_urn": json.loads(storage["glv_device"])["urn"], "access_token": access, "refresh_token": json.loads(storage["glovo_refresh_token"])}


def sign_in(ask, tell, lat, lon):
    """Sign in with e-mail and password, the one route Glovo's web client offers that carries no captcha."""
    device = str(uuid4())
    headers = _headers(lat, lon, True)
    headers["glovo-device-urn"] = fetch(f"{API}/identity/v4/devices", headers, {"fingerprints": [{"provider": "CWUID", "fingerprint": device}]}, acting=True)["urn"]
    email = ask("E-mail address on your Glovo account: ").strip()
    ways = [str(way) for way in fetch(f"{API}/v3/customers/auth/{urlquote(email)}/methods", headers, acting=True)["data"]["authenticationMethods"]]
    if not ways:
        raise RuntimeError("Glovo knows no account with that e-mail address. An account opened with a phone number signs in through a browser window: login glovo --browser.")
    if "PASSWORD" not in ways:
        raise RuntimeError(f"That Glovo account signs in with {', '.join(ways)} and has no password. A code sent to a phone carries a captcha this tool "
                           "does not solve, so sign in through a browser window instead: login glovo --browser.")
    try:
        reply = fetch(f"{API}/oauth/token", headers, {"grantType": "password", "username": email, "password": ask("Password: ", secret=True)}, acting=True)
    except RuntimeError as refusal:
        if getattr(refusal, "status", None) == 401:
            raise RuntimeError("Glovo did not accept that password.") from refusal
        raise
    if "access" not in reply:
        raise RuntimeError("Glovo asks for a second step on this sign-in, and that step carries a captcha this tool does not solve. "
                           "Sign in through a browser window instead: login glovo --browser.")
    return {"device_id": device, "device_urn": headers["glovo-device-urn"],
            "access_token": reply["access"]["accessToken"], "refresh_token": reply["access"]["refreshToken"]}


def whoami(session, lat, lon):
    """Who is signed in, and whether they hold Glovo Prime."""
    me = fetch(f"{API}/v3/me", _headers(lat, lon, True, account=True), acting=True)
    prime = fetch(f"{API}/customers/{me['id']}/subscription/status", _headers(lat, lon, True, account=True), acting=True)
    return {"who": me.get("name") or me.get("email") or "your account", "member": bool(prime.get("isSubscribed")), "plan": "Glovo Prime"}


def sign_out(session, lat, lon):
    fetch(f"{API}/oauth/revoke", _headers(lat, lon, True), {"token": session["refresh_token"]}, acting=True)
