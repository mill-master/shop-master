"""Glovo, read through the calls its own web client makes. No login is involved.

Glovo prices a basket only for a signed-in customer. The service fee, the small-basket surcharge and a store's basket-wide offers are therefore built from the parameters it publishes with each store, and have not been checked against a priced order.
"""

import re
import time
from urllib.parse import quote as urlquote
from uuid import uuid4

from net import fetch

API = "https://api.glovoapp.com"

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

_places = {}


def place(lat, lon):
    """Glovo's own reading of the delivery point: its city and country codes and the city's name."""
    if (lat, lon) not in _places:
        _places[lat, lon] = fetch(f"{API}/v3/addresslookup/pub/coordinates?latitude={lat}&longitude={lon}&allowFallback=true", _headers(lat, lon))
    return _places[lat, lon]


def _headers(lat, lon, located=False):
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
    """Products matching `query`, store by store (restaurant by restaurant for `food`). Glovo answers with its search screen: a card per store, followed by a row of that store's matching products."""
    category = f"&categoryId={FOOD_CATEGORY}" if food else ""
    reply = fetch(f"{API}/v1/web/store_wall/search?searchQuery={urlquote(query)}{category}", _headers(lat, lon, True),
                  {"searchContext": {"searchId": str(uuid4())}})
    hits, card = [], None
    for element in reply["data"]["body"]["data"]["elements"]:
        if element["type"] == "STORE_CARD_V2":
            state = _find(element, "shopIsOpen")  # the card's display event carries the store's state
            title = ((element["data"].get("title") or {}).get("text") or {}).get("text")
            card = {"store": element["data"]["slug"], "name": title or element["data"]["slug"], "open": state["shopIsOpen"] == "true"}
            if (state["glovoCategoryId"] == FOOD_CATEGORY) != food:
                card = None
        elif element["type"] == "CAROUSEL" and card:
            for product in element["data"]["elements"]:
                shown = (product["data"].get("pricing") or {}).get("finalPrice")
                if shown:
                    # A display string such as "4,49 ₾".
                    hits.append({**card, "price": _minor(float(re.sub(r"[^\d,]", "", shown).replace(",", ".")))})
            card = None
    return hits


def shelf(store, query, lat, lon, limit=8):
    """The best matches for `query` in one store."""
    reply = fetch(f"{API}/v3/stores/{store['store_id']}/addresses/{store['address_id']}/search?query={urlquote(query)}", _headers(lat, lon, True))
    offers = []
    for group in reply.get("results", []):
        for product in group.get("products", []):
            offer = {
                "id": str(product["id"]),
                "name": product["name"].strip(),
                "price": _minor(product["price"]),
                "note": (product.get("description") or "").strip() or None,
            }
            promotion = product.get("promotion") or {}
            if promotion.get("price") and not promotion.get("isPrime"):
                offer["was"], offer["price"] = offer["price"], _minor(promotion["price"])
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
        fees.append({"label": "Service fee", "segments": [[0, low / rate, low, 0], [low / rate, high / rate, 0, rate], [high / rate, None, high, 0]]})
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
    city = found["addressComponents"]["administrative_area_level_1"].lower()
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
