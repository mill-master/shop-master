"""Bolt Food, read through the calls its own web client makes.

Bolt shows an anonymous visitor a store's delivery price and nothing else: its small-order, service and packaging fees appear after sign-in. A Bolt basket total built here is a lower bound.
"""

from urllib.parse import urlencode
from uuid import uuid4

from net import fetch
from units import measure, money

HOST = "https://deliveryuser.live.boltsvc.net"
API = f"{HOST}/deliveryClient/public"
CLIENT = urlencode({
    "version": "FW.1.123.0", "language": "en-US", "deviceId": str(uuid4()),
    "deviceType": "web", "device_name": "web", "device_os_version": "web",
})
PREVIEW_BATCH = 20  # providers per preview request, as the web client sends them
PREVIEWED = 40      # search results looked into; Bolt ranks the relevant providers first

# Said to a shopper who asks to sign in. On 2026-11-27 Bolt answered the one sign-in tried with a real account, by phone number and texted code, with BLOCKED_BY_FRAUD.
NO_SIGN_IN = ("Bolt Food is read signed out only. Its fraud protection refused a sign-in from this tool on a real account, "
              "and the tool neither tries again nor looks for a way past it.")


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
    try:
        providers = call("deliverySearch", {**where, "search_string": query, "filters": [], "search_tab_id": tab})["providers"][:PREVIEWED]
    except RuntimeError as refusal:
        if "CITY_NOT_FOUND" in str(refusal):
            raise RuntimeError("Bolt Food does not deliver to this point") from refusal
        raise
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
