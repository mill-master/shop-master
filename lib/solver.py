"""Cheapest way to buy a shopping list from delivery stores, fees included.

A store charges for its own basket: the goods, plus fees that depend on that basket's subtotal. A fee is a list of segments [low, high, a, b], read as "a + b * subtotal while low <= subtotal < high" (high None means no upper end), in minor currency units. That one shape covers a flat delivery price, a surcharge that tops a small basket up to a minimum, a percentage service fee with a floor and a cap, free delivery above a threshold, and a discount (a negative amount).

The search tries every group of up to `max_stores` stores and every way of dividing the list among them. Shelf prices alone are a poor guide: moving one item can lift a basket over a threshold or strand another basket below one.
"""

from itertools import combinations
from math import floor

# Divisions examined per group of stores before the search starts fixing items in place.
LEAF_CAP = 1 << 16


def fee_amount(segments, subtotal):
    for low, high, a, b in segments:
        if subtotal >= low and (high is None or subtotal < high):
            return floor(a + b * subtotal + 0.5)
    return 0


def fee_lines(store, subtotal):
    """Non-zero fees of one basket as (label, amount) pairs."""
    lines = []
    for fee in store["fees"]:
        amount = fee_amount(fee["segments"], subtotal)
        if amount:
            lines.append((fee["label"], amount))
    return lines


def next_threshold(store, subtotal):
    """The nearest larger subtotal at which this basket's fees fall, as (extra_goods, fees_saved), or None.

    When the two numbers are equal the fee was buying nothing: goods worth that much cost no more than paying it.
    """
    now = sum(amount for _, amount in fee_lines(store, subtotal))
    marks = set()
    for fee in store["fees"]:
        for low, high, _, _ in fee["segments"]:
            marks.add(low)
            if high is not None:
                marks.add(high)
    for mark in sorted(m for m in marks if m > subtotal):
        saved = now - sum(amount for _, amount in fee_lines(store, mark))
        if saved > 0:
            return mark - subtotal, saved
    return None


def _best_division(group, wants, memo):
    """Cheapest division of `wants` among the stores of `group` that leaves no store empty."""
    fixed = [0] * len(group)
    assigned = {}
    free = []
    missing = []
    for want in wants:
        options = [(i, store["prices"][want]) for i, store in enumerate(group) if want in store["prices"]]
        if not options:
            missing.append(want)
        elif len(options) == 1:
            i, price = options[0]
            fixed[i] += price
            assigned[want] = i
        else:
            free.append((want, options))

    leaves = 1
    for _, options in free:
        leaves *= len(options)
    approximate = leaves > LEAF_CAP
    if approximate:
        # The wants whose price differs most between stores are the least likely to move for a fee's sake, so they are the ones fixed at their cheapest store.
        free.sort(key=lambda f: max(p for _, p in f[1]) - min(p for _, p in f[1]))
        while leaves > LEAF_CAP:
            want, options = free.pop()
            i, price = min(options, key=lambda o: o[1])
            fixed[i] += price
            assigned[want] = i
            leaves //= len(options)

    def fees(i, subtotal):
        key = (group[i]["ref"], subtotal)
        if key not in memo:
            memo[key] = sum(amount for _, amount in fee_lines(group[i], subtotal))
        return memo[key]

    best_cost = None
    best_choice = None
    subtotals = fixed[:]
    choice = [0] * len(free)

    def descend(k):
        nonlocal best_cost, best_choice
        if k == len(free):
            if 0 in subtotals:
                return  # a division that empties a store belongs to a smaller group
            cost = sum(subtotals) + sum(fees(i, x) for i, x in enumerate(subtotals))
            if best_cost is None or cost < best_cost:
                best_cost, best_choice = cost, choice[:]
            return
        for i, price in free[k][1]:
            subtotals[i] += price
            choice[k] = i
            descend(k + 1)
            subtotals[i] -= price

    descend(0)
    if best_cost is None:
        return None
    for (want, _), i in zip(free, best_choice):
        assigned[want] = i
    return best_cost, assigned, missing, approximate


def plans(wants, stores, max_stores=2):
    """Every worthwhile way to buy `wants`, best first.

    wants: the want keys.
    stores: [{"ref", "fees", "prices": {want: amount}}], each price already multiplied by the quantity wanted.

    A plan covering more of the list ranks above one covering less, then the cheaper total wins. A plan is dropped when some of its own stores, used alone, cover as much for no more money, so a split appears only where it pays or covers more.
    """
    memo = {}
    found = []
    for size in range(1, max_stores + 1):
        for group in combinations(stores, size):
            result = _best_division(group, wants, memo)
            if result is None:
                continue
            cost, assigned, missing, approximate = result
            baskets = []
            for i, store in enumerate(group):
                items = [want for want in wants if assigned.get(want) == i]
                subtotal = sum(store["prices"][want] for want in items)
                fees = fee_lines(store, subtotal)
                baskets.append({
                    "ref": store["ref"],
                    "wants": items,
                    "subtotal": subtotal,
                    "fees": fees,
                    "total": subtotal + sum(amount for _, amount in fees),
                    "next_threshold": next_threshold(store, subtotal),
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
