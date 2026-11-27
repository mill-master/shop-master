"""Wolt, read through the calls its own web client makes.

Wolt prices any basket for an anonymous visitor, so a store's fees are read from Wolt's own arithmetic, and a finished basket can be priced exactly, the store's standing offers included. Signed in, the same pricing is the account's own.
"""

import re
import time
from math import floor
from urllib.parse import parse_qs, quote as urlquote, urlsplit
from uuid import uuid4

from net import fetch
from units import measure

SEARCH = "https://restaurant-api.wolt.com/v1/pages/search"
AUTH = "https://authentication.wolt.com"
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

NEW_CUSTOMER = re.compile(r"new (user|customer)|first order", re.I)

# The signed-in session, when there is one, and what to call after it changes so that it is kept. Both are set by the command-line tool.
ACCOUNT = None
keep = lambda: None  # noqa: E731


def _half_up(amount):
    return floor(amount + 0.5)


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
                # The search reply does not say whether a store is taking orders: open ones too come without a delivery time.
                "open": None,
                "price": item["price"],
            })
    return hits


def _required_choices(bindings, definitions):
    """The cheapest way through a dish's obligatory choices: (what it adds to the price, the choices as checkout wants them).

    The added price is None when a choice is obligatory and its values were not sent with the menu.
    """
    added, stated = 0, []
    for binding in bindings:
        setup = binding.get("multi_choice_config") or {}
        needed = (setup.get("total_range") or {}).get("min") or 0
        if not needed or binding.get("prerequisite_values"):
            continue
        values = sorted((definitions.get(binding["option_id"]) or {}).get("values") or [], key=lambda value: value.get("price") or 0)
        if not values:
            return None, []
        repeats = setup.get("max_single_selections") or 1
        chosen = []
        for value in values:
            take = min(repeats, needed - sum(count for _, count in chosen))
            if take <= 0:
                break
            chosen.append((value, take))
        added += sum((value.get("price") or 0) * count for value, count in chosen)
        stated.append({"id": binding["id"], "values": [{"id": value["id"], "count": count, "price": value.get("price") or 0} for value, count in chosen]})
    return added, stated


def shelf(store, query, lat, lon, limit=8):
    """The best matches for `query` on one store's own shelves.

    The store's search returns hundreds of loosely related items after the relevant few, so only the head of its ranking is kept.
    """
    reply = fetch(f"{ASSORTMENT}/{store['key']}/assortment/items/search?language=en", HEADERS, {"q": query})
    definitions = {option["id"]: option for option in reply.get("options", [])}
    offers = []
    for item in reply.get("items", []):
        if item.get("disabled_info") or item.get("purchasable_balance") == 0:
            continue
        offer = {
            "id": item["id"],
            "name": item["name"].strip(),
            "base": item["price"],
            "price": item["price"],
            "list": item.get("original_price") or item["price"],
            # The name is what the shopper reads, and some stores' size labels belong to another product.
            "size": measure(item["name"]) or measure(item.get("unit_info")),
            "stock": item.get("purchasable_balance"),
            "note": (item.get("description") or "").strip() or None,
        }
        by_weight = item.get("sell_by_weight_config")
        if by_weight:
            # Sold by weight in steps: one step is the unit bought, at its share of the price per kilogram.
            step = by_weight["grams_per_step"]
            offer.update(weighed=True, size=[step, "g"], stock=None,
                         base=_half_up(by_weight["price_per_kg"] * step / 1000),
                         price=_half_up(by_weight["price_per_kg"] * step / 1000),
                         list=_half_up((item.get("original_price") or by_weight["price_per_kg"]) * step / 1000))
        added, stated = _required_choices(item.get("options") or [], definitions)
        if item.get("options"):
            # A dish with choices: its price starts at the dish plus the cheapest obligatory ones.
            offer["from"] = True
            if added:
                offer.update(extra=added, choices=stated, price=offer["price"] + added, list=offer["list"] + added)
        cut = store["item_offers"].get(item["id"])
        if cut and cut[1] <= 1:
            # A store campaign on this product. The shelf shows the price before it; checkout takes it off.
            offer["price"] -= _half_up(offer["price"] * cut[0])
        elif cut:
            offer["bulk"] = [cut[1], cut[0]]
        offers.append(offer)
        if len(offers) == limit:
            break
    return offers


def _checkout(store, items, lat, lon):
    """Wolt's pricing of a basket: the page its web client shows before payment. Nothing is ordered or stored."""
    return fetch(f"{ORDER_XP}/v2/pages/checkout", _acting(), {"purchase_plan": {
        "venue": {"id": store["venue_id"], "currency": store["currency"], "country": store["country"]},
        "delivery_method": "homedelivery",
        "menu_items": [{"options": [], "restrictions": [], "exclude_from_discounts": False, "category_id": item["id"], **item} for item in items],
        "delivery": {"delivery_coordinates": {"latitude": lat, "longitude": lon}},
        "use_promo_discount_ids": store["offer_ids"], "use_promo_surcharge_ids": [], "payment_methods": [],
        "courier_tip": 0, "use_loyalty_points_amount": 0,
        "use_cash": False, "use_credits_and_tokens": False, "is_priority_delivery": False, "is_cart": True,
    }})


def quote(store, lines, lat, lon):
    """Wolt's own pricing of a basket. `lines` holds (offer, count) pairs.

    Returns what Wolt charges for the goods once the store's offers open to every customer are applied, the fees as (label, amount) pairs, and the names of the offers applied.
    """
    items = []
    for offer, count in lines:
        each = offer["base"] + offer.get("extra", 0)
        if offer.get("weighed"):
            items.append({"id": offer["id"], "count": 1, "base_price": each * count, "end_amount": each * count, "is_weighted_item": True})
        else:
            items.append({"id": offer["id"], "count": count, "base_price": offer["base"], "end_amount": each * count, "options": offer.get("choices", [])})
    rows = _checkout(store, items, lat, lon)["checkout_rows"]
    priced = {"goods": None, "fees": [], "offers": [row["label"] for row in rows if row.get("template") == "discount_row"]}
    for row in rows:
        if row.get("template") == "price_total_amount_row":
            break  # what follows the total repeats the offers already counted above it
        if row.get("template") != "amount_row":
            continue
        if row["label"] == "Item subtotal":
            priced["goods"] = row["amount"]["amount"]
        else:
            priced["fees"].append((row["label"], row["amount"]["amount"]))
    return priced


def audience(offer):
    """Whom a store offer is limited to, or None when any customer may use it."""
    if offer["conditions"].get("has_wolt_plus"):
        return "Wolt+ members"
    # Wolt marks a new-customer offer in its wording alone.
    if any(NEW_CUSTOMER.search(point) for point in offer["description"].get("points") or []):
        return "new customers"
    return None


def offer_segments(offer, delivery):
    """A basket-wide offer's discount as solver segments, or None when it depends on more than the basket's size.

    An offer on delivery with no minimum is left to the delivery price Wolt quotes, which already carries it.
    """
    conditions = offer["conditions"]
    needs = conditions.get("basket_contains") or []
    methods = conditions.get("delivery_methods")
    if any(value for key, value in conditions.items() if key not in ("basket_contains", "delivery_methods")) \
            or (methods and "homedelivery" not in methods) \
            or any(need.get("any_of_items") or need.get("items_from_categories") or need.get("min_quantity") for need in needs):
        return None
    low = max((need.get("min_amount") or 0 for need in needs), default=0)
    goods, carriage = offer["effects"].get("basket_discount"), offer["effects"].get("delivery_discount")
    if goods and goods.get("fraction"):
        cap = goods.get("max_amount")
        if not cap:
            return [[low, None, 0, -goods["fraction"]]]
        full = cap / goods["fraction"]  # the subtotal at which the discount reaches its cap
        return ([[low, full, 0, -goods["fraction"]]] if full > low else []) + [[max(low, full), None, -cap, 0]]
    if goods:
        return [[low, None, -goods["amount"], 0]]
    if carriage and low:
        return [[low, None, -min(delivery, round(delivery * (carriage.get("fraction") or 0)) + (carriage.get("amount") or 0)), 0]]
    return None


def schedule(minimum, price_ranges, probe):
    """A store's fee rules as solver segments, from its published numbers and Wolt's pricing of a near-empty basket.

    Checkout charges a service fee that is a share of the goods between a floor and a cap, a surcharge that tops a small basket up to the store minimum without exceeding a cap of its own, and delivery and bag charges that ignore the basket. The surcharge looks at the goods' prices before discounts, and its cap is not published with the store, which is why a basket is priced to read it. `probe` is that pricing: the fees of a basket worth one minor unit.
    """
    fees = [{"label": "Delivery", "segments": [[0, None, probe["delivery"], 0]]}]

    service = []
    for band in price_ranges:
        low, high = band["min"], band["max"] or None
        if band["b"] >= 0:
            service.append([low, high, band["a"], band["b"]])
        elif high is None:
            raise RuntimeError("Wolt published a falling service-fee band with no end, which this reading of its fees does not cover")
        else:
            # The published first band still falls as the basket grows; checkout charges its end value throughout.
            service.append([low, high, band["a"] + band["b"] * high, 0])
    fees.append({"label": "Service fee", "segments": service})

    cap = probe["small_order"]
    if cap >= minimum - 1:
        fees.append({"label": "Small order fee", "on": "list", "segments": [[0, minimum, minimum, -1]]})
    elif cap:
        fees.append({"label": "Small order fee", "on": "list", "segments": [[0, minimum - cap, cap, 0], [minimum - cap, minimum, minimum, -1]]})

    if probe["bag"]:
        # One bag; Wolt adds another for every further ten items.
        fees.append({"label": "Bag", "segments": [[0, None, probe["bag"], 0]]})
    return fees


def store(key, lat, lon):
    """One store as it stands for this delivery point: state, fee rules, standing offers."""
    static = fetch(f"{ORDER_XP}/v1/pages/venue/slug/{urlquote(key)}/static", HEADERS)["venue"]
    dynamic = fetch(f"{ORDER_XP}/v1/venue/slug/{urlquote(key)}/dynamic/?lat={lat}&lon={lon}", _acting())
    venue, raw = dynamic["venue"], dynamic["venue_raw"]
    # For a signed-in account Wolt itself knows which campaigns apply, so all of them are put to it.
    campaigns = [campaign for campaign in raw.get("discounts", []) if ACCOUNT or not audience(campaign)]
    record = {
        "name": static["name"].strip(),
        "url": static["share_url"],
        "currency": static["currency"],
        "venue_id": static["id"],
        "country": static["country"],
        "open": bool(venue["delivery_open_status"]["is_open"] and venue["online"]),
        "opens": venue["open_status"]["value"],
        "eta": next(((option.get("estimate") or {}).get("label") for option in venue["delivery_configs"] if option["schedule"] == "standard"), None),
        "rating": (static.get("rating") or {}).get("score"),
        "caveat": None,
        # Every campaign a returning customer may use goes to checkout with each basket; checkout applies those that fit.
        "offer_ids": [campaign["id"] for campaign in campaigns],
        "item_offers": {},
        "notes": [],
    }
    for campaign in campaigns:
        cut = campaign["effects"].get("item_discount")
        if cut and cut.get("fraction"):
            units = max((need.get("min_quantity") or 1 for need in campaign["conditions"].get("basket_contains") or []), default=1)
            for item_id in (cut.get("include") or {}).get("items") or []:
                record["item_offers"][item_id] = [cut["fraction"], units]

    priced = _checkout(record, [{"id": "0" * 24, "count": 1, "base_price": 1, "end_amount": 1}], lat, lon)
    distance = next((re.search(r"\((.+)\)", row["label"]) for row in priced["checkout_rows"]
                     if row.get("template") == "amount_row" and row["label"].startswith("Delivery")), None)
    record["distance"] = distance.group(1) if distance else None
    specs = raw["delivery_specs"]
    record["fees"] = schedule(specs["order_minimum_no_surcharge"], specs["delivery_pricing"]["price_ranges"], {
        "delivery": priced["telemetry"]["delivery_price"],
        "small_order": priced["telemetry"]["small_order_fee"],
        "bag": priced["purchase_validation"].get("bag_fee") or 0,
    })

    # Wolt applies one basket-wide offer at a time. Where a store runs several for every customer, this estimate counts them all and the pricing of the finished basket corrects it.
    for offer in raw.get("discounts", []):
        if not (offer["effects"].get("basket_discount") or offer["effects"].get("delivery_discount")):
            continue
        title, limited = offer["description"]["title"], audience(offer)
        segments = None if limited else offer_segments(offer, priced["telemetry"]["delivery_price"])
        if segments:
            record["fees"].append({"label": f"Offer: {title}", "segments": segments})
        record["notes"].append(f"offer: {title}" + (f" ({limited}; not counted)" if limited else " (counted in the totals)" if segments
                                                    else " (applied when Wolt prices the basket)"))
    if record["item_offers"]:
        record["notes"].append(f"{len(record['item_offers'])} products are under a store campaign; a candidate's price already has its discount, or says from how many units it applies")
    return record


# --- the shopper's own account ------------------------------------------------

def _acting():
    """Request headers: the signed-in account's when there is one."""
    return authorized(ACCOUNT) if ACCOUNT else HEADERS


def _link_token(link):
    """The sign-in token inside the link Wolt e-mails, which can sit a few redirects deep."""
    for _ in range(4):
        query = parse_qs(urlsplit(link.strip()).query)
        if "token" in query:
            return query["token"][0]
        link = next((value[0] for value in query.values() if "://" in value[0]), "")
    raise RuntimeError("That link carries no sign-in token. Copy the address of the button in Wolt's e-mail, without opening it.")


def _session(reply):
    return {"refresh_token": reply["refresh_token"], "access_token": reply["access_token"], "expires_at": time.time() + reply.get("expires_in", 0)}


def sign_in(ask, tell, lat, lon):
    """Sign in with the link Wolt e-mails. Asking Wolt to send it carries a captcha, so the shopper asks; redeeming it is a plain call."""
    tell("Wolt signs you in with a link it e-mails. Ask for one at https://wolt.com/en/login with your e-mail address. "
         "When the e-mail arrives, copy the address of its button without opening it (the link works once), and paste it here.")
    grant = {"grant_type": "email_login", "token": _link_token(ask("Link from Wolt's e-mail: ")), "audience": "wolt-com", "capabilities": "access_confirmation"}
    try:
        return _session(fetch(f"{AUTH}/v1/wauth2/access_token", HEADERS, form=grant))
    except RuntimeError as refusal:
        answer = getattr(refusal, "reply", None)
        code = answer.get("error_code") if isinstance(answer, dict) else None
        if code == 126:
            raise RuntimeError("Wolt did not accept that link: it has expired or was already opened. Ask for a new one.") from refusal
        if code != 130:
            raise
    # Wolt wants this sign-in confirmed with a code it e-mails.
    confirming = {**HEADERS, "authorization": f"Bearer {answer['access_confirmation_token']}"}
    fetch(f"{AUTH}/v1/access_confirmation/email", confirming, {})
    fetch(f"{AUTH}/v1/access_confirmation/email/submit", confirming, {"code": ask("Wolt e-mailed a confirmation code. Code: ").strip()})
    grant = {"grant_type": "access_confirmation_token", "access_confirmation_token": answer["access_confirmation_token"], "audience": "wolt-com"}
    return _session(fetch(f"{AUTH}/v1/wauth2/access_token", HEADERS, form=grant))


def authorized(session):
    """Request headers that act for the signed-in account. An access token about to lapse is renewed first, and the session kept."""
    if session["expires_at"] - time.time() < 120:
        reply = fetch(f"{AUTH}/v1/wauth2/access_token", HEADERS, form={"grant_type": "refresh_token", "refresh_token": session["refresh_token"]})
        # Wolt can replace the refresh token on use, after which the old one is dead: the new one is stored before anything else happens.
        session.update(access_token=reply["access_token"], expires_at=time.time() + reply.get("expires_in", 0),
                       refresh_token=reply.get("refresh_token") or session["refresh_token"])
        keep()
    return {**HEADERS, "authorization": f"Bearer {session['access_token']}"}


def whoami(session, lat, lon):
    """Who is signed in, and whether they hold Wolt+."""
    user = fetch("https://restaurant-api.wolt.com/v1/user/me", authorized(session))["user"]
    held = fetch(f"https://consumer-api.wolt.com/subscriptions-api/v1/subscriptions?current_location_country={user.get('country', '')}",
                 authorized(session)).get("subscriptions", [])
    today = time.strftime("%Y-%m-%d")
    plan = next((plan for plan in held if (plan.get("paid_until_date") or "")[:10] >= today), None)
    name = " ".join(part for part in ((user.get("name") or {}).get("first_name"), (user.get("name") or {}).get("last_name")) if part)
    return {"who": name or user.get("email") or "your account", "member": bool(plan), "plan": ((plan or {}).get("plan") or {}).get("name") or "Wolt+"}


def sign_out(session, lat, lon):
    fetch(f"{AUTH}/v1/wauth2/logout", authorized(session), {"refresh_tokens": [session["refresh_token"]]})
