"""Wolt, read through the calls its own web client makes. No login is involved.

Wolt prices any basket for an anonymous visitor, so a store's fees are read from Wolt's own arithmetic, and a finished basket can be priced exactly.
"""

import re
from urllib.parse import quote as urlquote
from uuid import uuid4

from net import fetch

SEARCH = "https://restaurant-api.wolt.com/v1/pages/search"
ORDER_XP = "https://consumer-api.wolt.com/order-xp/web"
ASSORTMENT = "https://consumer-api.wolt.com/consumer-api/consumer-assortment/v1/venues/slug"

# The header set of Wolt's web client. The session id is the value that client sends when analytics consent is declined.
HEADERS = {
    "app-language": "en",
    "platform": "Web",
    "client-version": "1.16.79",
    "clientversionnumber": "1.16.79",
    "w-wolt-session-id": "no-analytics-consent",
    "x-wolt-web-clientid": str(uuid4()),
}

PER_UNITS = {"kilogram": "kg", "litre": "l", "piece": "pc"}


def discover(query, lat, lon, food):
    """Items matching `query` in the stores (or, for `food`, the restaurants) that deliver to the point, in Wolt's own ranking."""
    reply = fetch(SEARCH, HEADERS, {"q": query, "target": "items", "lat": lat, "lon": lon})
    hits = []
    for section in reply.get("sections", []):
        for entry in section.get("items", []):
            item = (entry.get("link") or {}).get("menu_item_details")
            if not item or (entry.get("menu_item") or {}).get("is_available") is False:
                continue
            if (item.get("product_line") == "restaurant") != food:
                continue
            hits.append({
                "store": item["venue_slug"],
                "name": item["venue_name"].strip(),
                # Wolt leaves the delivery estimate empty for a store that is not taking orders now.
                "open": bool(item.get("estimate_range")),
                "price": item["price"],
            })
    return hits


def shelf(store, query, lat, lon, limit=8):
    """The best matches for `query` on one store's own shelves.

    The store's search returns hundreds of loosely related items after the relevant few, so only the head of its ranking is kept.
    """
    reply = fetch(f"{ASSORTMENT}/{store['key']}/assortment/items/search?language=en", HEADERS, {"q": query})
    offers = []
    for item in reply.get("items", []):
        if item.get("disabled_info") or item.get("purchasable_balance") == 0:
            continue
        per = item.get("unit_price") or {}
        by_weight = item.get("sell_by_weight_config")
        offers.append({
            "id": item["id"],
            "name": item["name"].strip(),
            # A weighed item is priced per kilogram, and its quantity is a weight.
            "price": by_weight["price_per_kg"] if by_weight else item["price"],
            "was": item.get("original_price"),
            "unit": f"sold in {by_weight['grams_per_step']} g steps" if by_weight else item.get("unit_info"),
            "per": [by_weight["price_per_kg"], "kg"] if by_weight
                   else [per["price"], PER_UNITS[per["unit"]]] if per.get("unit") in PER_UNITS and per.get("price") else None,
            "weighed": bool(by_weight),
            "stock": None if by_weight else item.get("purchasable_balance"),
            "note": (item.get("description") or "").strip() or None,
        })
        if len(offers) == limit:
            break
    return offers


def _checkout(store, lines, lat, lon):
    """Wolt's pricing of a basket: the page its web client shows before payment. Nothing is ordered or stored."""
    items = [{
        "id": item_id, "count": count, "base_price": price, "end_amount": price * count,
        "options": [], "restrictions": [], "exclude_from_discounts": False, "category_id": item_id,
    } for item_id, price, count in lines]
    return fetch(f"{ORDER_XP}/v2/pages/checkout", HEADERS, {"purchase_plan": {
        "venue": {"id": store["venue_id"], "currency": store["currency"], "country": store["country"]},
        "delivery_method": "homedelivery",
        "menu_items": items,
        "delivery": {"delivery_coordinates": {"latitude": lat, "longitude": lon}},
        "use_promo_discount_ids": [], "use_promo_surcharge_ids": [], "payment_methods": [],
        "courier_tip": 0, "use_loyalty_points_amount": 0,
        "use_cash": False, "use_credits_and_tokens": False, "is_priority_delivery": False, "is_cart": True,
    }})


def quote(store, lines, lat, lon):
    """The fee lines Wolt itself charges on a basket, as (label, amount) pairs. `lines` holds (offer, quantity) pairs.

    Promotions are left out: Wolt offers an anonymous visitor its new-customer deals.
    """
    priced = []
    for offer, quantity in lines:
        if offer.get("weighed") or quantity != int(quantity):
            priced.append((offer["id"], round(offer["price"] * quantity), 1))
        else:
            priced.append((offer["id"], offer["price"], int(quantity)))
    rows = _checkout(store, priced, lat, lon)["checkout_rows"]
    return [(row["label"], row["amount"]["amount"]) for row in rows
            if row.get("template") == "amount_row" and row["label"] != "Item subtotal"]


def schedule(minimum, price_ranges, probe):
    """A store's fee rules as solver segments, from its published numbers and Wolt's pricing of a near-empty basket.

    Checkout charges a service fee that is a share of the subtotal between a floor and a cap, a surcharge that tops a small basket up to the store minimum without exceeding a cap of its own, and delivery and bag charges that ignore the subtotal. The surcharge cap is not published with the store, which is why a basket is priced to read it. `probe` is that pricing: the fees of a basket worth one minor unit.
    """
    fees = [{"label": "Delivery", "segments": [[0, None, probe["delivery"], 0]]}]

    service = []
    for band in price_ranges:
        low, high = band["min"], band["max"] or None
        if band["b"] < 0:
            # The published first band still falls as the basket grows; checkout charges its end value throughout.
            service.append([low, high, band["a"] + band["b"] * high, 0])
        else:
            service.append([low, high, band["a"], band["b"]])
    fees.append({"label": "Service fee", "segments": service})

    cap = probe["small_order"]
    if cap >= minimum - 1:
        fees.append({"label": "Small order fee", "segments": [[0, minimum, minimum, -1]]})
    elif cap:
        fees.append({"label": "Small order fee", "segments": [[0, minimum - cap, cap, 0], [minimum - cap, minimum, minimum, -1]]})

    if probe["bag"]:
        # One bag; Wolt adds another for every further ten items.
        fees.append({"label": "Bag", "segments": [[0, None, probe["bag"], 0]]})
    return fees


def store(key, lat, lon):
    """One store as it stands for this delivery point: state, fee rules, standing offers."""
    static = fetch(f"{ORDER_XP}/v1/pages/venue/slug/{urlquote(key)}/static", HEADERS)["venue"]
    dynamic = fetch(f"{ORDER_XP}/v1/venue/slug/{urlquote(key)}/dynamic/?lat={lat}&lon={lon}", HEADERS)
    venue, raw = dynamic["venue"], dynamic["venue_raw"]
    record = {
        "name": static["name"].strip(),
        "url": static["share_url"],
        "currency": static["currency"],
        "venue_id": static["id"],
        "country": static["country"],
        "open": venue["delivery_open_status"]["is_open"] and venue["online"],
        "opens": venue["open_status"]["value"],
        "eta": next((c["estimate"]["label"] for c in venue["delivery_configs"] if c["schedule"] == "standard"), None),
        "rating": (static.get("rating") or {}).get("score"),
        "caveat": None,
    }

    priced = _checkout(record, [("0" * 24, 1, 1)], lat, lon)
    distance = next((re.search(r"\((.+)\)", row["label"]) for row in priced["checkout_rows"]
                     if row.get("template") == "amount_row" and row["label"].startswith("Delivery")), None)
    record["distance"] = distance.group(1) if distance else None
    specs = raw["delivery_specs"]
    record["fees"] = schedule(specs["order_minimum_no_surcharge"], specs["delivery_pricing"]["price_ranges"], {
        "delivery": priced["telemetry"]["delivery_price"],
        "small_order": priced["telemetry"]["small_order_fee"],
        "bag": priced["purchase_validation"].get("bag_fee") or 0,
    })

    # Offers on the whole basket or on delivery are listed, not applied: several are for new customers only, and Wolt says so in words alone.
    record["notes"] = [
        "offer: " + " | ".join([offer["description"]["title"], *(offer["description"].get("points") or [])])[:150]
        for offer in raw.get("discounts", [])
        if offer["effects"].get("basket_discount") or offer["effects"].get("delivery_discount")
    ]
    return record
