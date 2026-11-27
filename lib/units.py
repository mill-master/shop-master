"""Sizes of goods and written prices: how much one pack holds, how much a shopper asked for, and what a price label says.

A size is a pair [amount, unit] with the unit one of "g", "ml" and "pc", so that packs and requests of one kind compare directly.
"""

import re
from math import ceil

# Spellings met on the three platforms' shelves, Georgian and Latin, with the factor that turns each into its base unit.
UNITS = {
    "kg": (1000, "g"), "კგ": (1000, "g"),
    "g": (1, "g"), "gr": (1, "g"), "გრ": (1, "g"), "გ": (1, "g"),
    "l": (1000, "ml"), "lt": (1000, "ml"), "ლ": (1000, "ml"),
    "ml": (1, "ml"), "მლ": (1, "ml"),
    "pcs": (1, "pc"), "pc": (1, "pc"), "pieces": (1, "pc"), "ცალიანი": (1, "pc"), "ცალი": (1, "pc"), "ც": (1, "pc"),
}
# A pack up to a tenth under the amount asked still answers it: 950 ml and 900 g packs are sold as the litre and the kilo.
SHORT = 0.9
NUMBER = r"\d+(?:[.,]\d+)?"
SIZE = re.compile(
    rf"(?<![\w.,])({NUMBER})\s*(?:[x×*]\s*({NUMBER})\s*)?({'|'.join(sorted(UNITS, key=len, reverse=True))})(?!\w)",
    re.IGNORECASE,
)


def _number(text):
    return float(text.replace(",", "."))


def measure(text):
    """The size a product name or label states, as [amount, unit], or None when it states none.

    A multiple ("6x1.5l") is taken as its product. Where a name carries several figures the first is the pack, except that a bare "1 pc" beside another size only says the pack is one item.
    """
    sizes = []
    for found in SIZE.finditer(text or ""):
        first, second, unit = found.groups()
        factor, base = UNITS[unit.lower()]
        amount = _number(first) * (_number(second) if second else 1) * factor
        # "0.75ml" on a wine and "0.25g" on a cheese are litres and kilograms mislabelled; a size under one unit is no size.
        if amount >= 1:
            sizes.append([round(amount, 3), base])
    told = [size for size in sizes if size != [1, "pc"]] or sizes
    return told[0] if told else None


def packs(wanted, size):
    """How many packs of `size` it takes to hold `wanted`, or None when the two cannot be compared."""
    if not size or size[1] != wanted[1]:
        return None
    return max(1, ceil(wanted[0] * SHORT / size[0] - 1e-9))


def money(text):
    """A written price such as "4,49 ₾", "₾4.49" or "1 234,50" in minor units.

    The last comma or point is the decimal mark when one or two digits follow it; any other is a thousands mark.
    """
    digits = re.sub(r"\s", "", re.search(r"\d[\d\s.,]*", text).group()).rstrip(".,")
    mark = max(digits.rfind("."), digits.rfind(","))
    whole, cents = (digits[:mark], digits[mark + 1:]) if mark != -1 and len(digits) - mark - 1 <= 2 else (digits, "")
    return int(re.sub(r"[.,]", "", whole) or 0) * 100 + int(cents.ljust(2, "0") or 0)


def per_unit(price, size):
    """A pack's price per kilogram, litre or piece, as (amount, unit name), or None without a size."""
    if not size:
        return None
    amount, unit = size
    scale, name = {"g": (1000, "kg"), "ml": (1000, "l"), "pc": (1, "pc")}[unit]
    return round(price * scale / amount), name
