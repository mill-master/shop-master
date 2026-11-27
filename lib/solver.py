"""Cheapest way to buy a shopping list from delivery stores, fees included.

A store charges for its own basket: the goods, plus fees that depend on that basket. A fee is a list of segments [low, high, a, b], read as "a + b * subtotal while low <= subtotal < high" (high None means no upper end), in minor currency units. That one shape covers a flat delivery price, a surcharge that tops a small basket up to a minimum, a percentage service fee with a floor and a cap, free delivery above a threshold, and an offer (a negative amount).

Goods have two values: what they cost (`paid`) and what they would cost without discounts (`listed`). A fee is reckoned on the first unless it carries "on": "list".

The search tries every group of up to `max_stores` stores and every way of dividing the list among them. Shelf prices alone are a poor guide: moving one item can lift a basket over a threshold or strand another basket below one.
"""

from itertools import combinations
from math import ceil, floor

# Steps the search may take on one group of stores. A division found by then is returned and marked approximate; lists of a few dozen items stay well inside it.
STEP_BUDGET = 2_000_000
# A threshold is worth pointing out when at least this share of the extra goods comes back in lower fees.
WORTHWHILE = 0.5


def fee_amount(segments, subtotal):
    for low, high, a, b in segments:
        if subtotal >= low and (high is None or subtotal < high):
            return floor(a + b * subtotal + 0.5)
    return 0


def fee_lines(store, paid, listed=None):
    """Non-zero fees of one basket as (label, amount) pairs."""
    lines = []
    for fee in store["fees"]:
        amount = fee_amount(fee["segments"], paid if listed is None or fee.get("on") != "list" else listed)
        if amount:
            lines.append((fee["label"], amount))
    return lines


def fee_total(store, paid, listed=None):
    return sum(amount for _, amount in fee_lines(store, paid, listed))


def next_threshold(store, paid, listed=None):
    """The nearest larger basket at which the fees fall enough to be worth reaching, as (extra_goods, fees_saved), or None.

    When the two numbers are equal the fee was buying nothing: goods worth that much cost no more than paying it.
    """
    listed = paid if listed is None else listed
    now = fee_total(store, paid, listed)
    steps = set()
    for fee in store["fees"]:
        at = listed if fee.get("on") == "list" else paid
        for low, high, _, _ in fee["segments"]:
            steps.update(ceil(mark - at) for mark in (low, high) if mark is not None and mark > at)
    for extra in sorted(steps):
        saved = now - fee_total(store, paid + extra, listed + extra)
        if saved >= WORTHWHILE * extra:
            return extra, saved
    return None


def _fee_floor(store, wants):
    """The least this store could charge in fees on any basket drawn from `wants`. A bound for the search, not a price."""
    most = {"paid": sum(store["lines"][want][0] for want in wants if want in store["lines"]),
            "list": sum(store["lines"][want][1] for want in wants if want in store["lines"])}
    floor_ = 0
    for fee in store["fees"]:
        top = most["list" if fee.get("on") == "list" else "paid"]
        # A fee is linear between its segment ends, so its least value over whole amounts lies at one of them.
        points = {0, top}
        for low, high, _, _ in fee["segments"]:
            points.update(point for point in (ceil(low), None if high is None else ceil(high) - 1) if point is not None and 0 <= point <= top)
        floor_ += min(fee_amount(fee["segments"], point) for point in points)
    return floor_


def _best_division(group, wants):
    """Cheapest division of `wants` among the stores of `group` that leaves no store empty.

    Items go to their cheapest store first, and a branch is dropped once its goods alone, with every store at its lowest possible fees, cannot beat the best division found. Fees move by a few units of currency while shelf prices differ by many, so little of the tree is walked.
    """
    choices, missing = [], []
    for want in wants:
        found = sorted((store["lines"][want][0], i, store["lines"][want][1]) for i, store in enumerate(group) if want in store["lines"])
        if found:
            choices.append((want, found))
        else:
            missing.append(want)
    # Items with the most to lose from a wrong store are placed first, so that poor branches end early.
    choices.sort(key=lambda choice: choice[1][0][0] - choice[1][1][0] if len(choice[1]) > 1 else float("-inf"))
    cheapest_rest = [0] * (len(choices) + 1)
    for k in range(len(choices) - 1, -1, -1):
        cheapest_rest[k] = cheapest_rest[k + 1] + choices[k][1][0][0]
    fees_floor = sum(_fee_floor(store, wants) for store in group)

    size = len(group)
    paid, listed, held = [0] * size, [0] * size, [0] * size
    placed = [0] * len(choices)
    best = {"cost": None, "placed": None, "steps": 0}

    def descend(k, goods):
        best["steps"] += 1
        if best["steps"] > STEP_BUDGET:
            return
        if best["cost"] is not None and goods + cheapest_rest[k] + fees_floor >= best["cost"]:
            return
        if k == len(choices):
            if 0 in held:
                return  # a division that empties a store belongs to a smaller group
            cost = goods + sum(fee_total(group[i], paid[i], listed[i]) for i in range(size))
            if best["cost"] is None or cost < best["cost"]:
                best["cost"], best["placed"] = cost, placed[:]
            return
        for price, i, full in choices[k][1]:
            paid[i] += price
            listed[i] += full
            held[i] += 1
            placed[k] = i
            descend(k + 1, goods + price)
            paid[i] -= price
            listed[i] -= full
            held[i] -= 1

    descend(0, 0)
    if best["cost"] is None:
        return None
    assigned = {want: i for (want, _), i in zip(choices, best["placed"])}
    return best["cost"], assigned, missing, best["steps"] > STEP_BUDGET


def plans(wants, stores, max_stores=2):
    """Every worthwhile way to buy `wants`, best first.

    wants: the want keys.
    stores: [{"ref", "fees", "lines": {want: (paid, listed)}}], each amount already multiplied by the quantity wanted.

    A plan covering more of the list ranks above one covering less, then the cheaper total wins. A plan is dropped when some of its own stores, used alone, cover as much for no more money, so a split appears only where it pays or covers more.
    """
    found = []
    for size in range(1, max_stores + 1):
        for group in combinations(stores, size):
            result = _best_division(group, wants)
            if result is None:
                continue
            cost, assigned, missing, approximate = result
            baskets = []
            for i, store in enumerate(group):
                items = [want for want in wants if assigned.get(want) == i]
                paid = sum(store["lines"][want][0] for want in items)
                listed = sum(store["lines"][want][1] for want in items)
                fees = fee_lines(store, paid, listed)
                baskets.append({
                    "ref": store["ref"],
                    "wants": items,
                    "subtotal": paid,
                    "fees": fees,
                    "total": paid + sum(amount for _, amount in fees),
                    "next_threshold": next_threshold(store, paid, listed),
                })
            found.append({"baskets": baskets, "missing": missing, "total": cost, "approximate": approximate})

    def refs(plan):
        return {basket["ref"] for basket in plan["baskets"]}

    kept = [
        plan for plan in found
        if not any(
            refs(other) < refs(plan)
            and len(other["missing"]) <= len(plan["missing"])
            and other["total"] <= plan["total"]
            for other in found
        )
    ]
    kept.sort(key=lambda plan: (len(plan["missing"]), plan["total"], len(plan["baskets"])))
    return kept
