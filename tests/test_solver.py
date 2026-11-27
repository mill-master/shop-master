import random
import sys
import unittest
from itertools import combinations, product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import solver  # noqa: E402


def store(ref, prices, delivery=0, minimum=0, extra_fees=()):
    """A store with a flat delivery price and a surcharge topping baskets up to `minimum`. `prices` holds paid amounts, or (paid, listed) pairs."""
    fees = [{"label": "Delivery", "segments": [[0, None, delivery, 0]]}]
    if minimum:
        fees.append({"label": "Small order", "segments": [[0, minimum, minimum, -1]]})
    fees.extend(extra_fees)
    lines = {want: price if isinstance(price, tuple) else (price, price) for want, price in prices.items()}
    return {"ref": ref, "fees": fees, "lines": lines}


def shape(plan):
    return {basket["ref"]: sorted(basket["wants"]) for basket in plan["baskets"]}


class FeeAmount(unittest.TestCase):
    def test_segment_bounds_are_low_inclusive_high_exclusive(self):
        segments = [[0, 1250, 1350, -1.0], [1250, 6238, 0, 0.08], [6238, None, 499, 0.0]]
        self.assertEqual(solver.fee_amount(segments, 0), 1350)
        self.assertEqual(solver.fee_amount(segments, 1249), 101)
        self.assertEqual(solver.fee_amount(segments, 1250), 100)
        self.assertEqual(solver.fee_amount(segments, 3000), 240)
        self.assertEqual(solver.fee_amount(segments, 6238), 499)
        self.assertEqual(solver.fee_amount(segments, 90000), 499)

    def test_no_segment_means_no_fee(self):
        self.assertEqual(solver.fee_amount([[0, 2500, 2500, -1]], 2500), 0)

    def test_half_rounds_up(self):
        self.assertEqual(solver.fee_amount([[0, None, 0, 0.5]], 5), 3)

    def test_a_fee_on_the_listed_value_ignores_what_was_paid(self):
        s = store("A", {}, minimum=2500)
        s["fees"][1]["on"] = "list"
        self.assertEqual(solver.fee_lines(s, 2196, 2500), [])
        self.assertEqual(solver.fee_lines(s, 2196, 2196), [("Small order", 304)])


class Plans(unittest.TestCase):
    def test_one_store_with_everything_beats_a_split_that_pays_two_sets_of_fees(self):
        wants = ["milk", "eggs", "bread", "rice", "spice"]
        everything = store("A", {"milk": 550, "eggs": 590, "bread": 250, "rice": 700, "spice": 450}, delivery=260, minimum=2500)
        cheaper_rice = store("B", {"rice": 600}, delivery=260, minimum=2500)
        best = solver.plans(wants, [everything, cheaper_rice])[0]
        self.assertEqual(shape(best), {"A": sorted(wants)})
        self.assertEqual(best["missing"], [])
        self.assertEqual(best["total"], 2540 + 260)

    def test_the_store_without_rice_is_paired_with_one_that_has_it(self):
        wants = ["milk", "eggs", "bread", "rice", "spice"]
        no_rice = store("A", {"milk": 550, "eggs": 590, "bread": 250, "spice": 450}, delivery=260)
        has_rice = store("B", {"rice": 700, "milk": 600, "eggs": 640}, delivery=260)
        best = solver.plans(wants, [no_rice, has_rice])[0]
        self.assertEqual(best["missing"], [])
        self.assertEqual(shape(best), {"A": ["bread", "eggs", "milk", "spice"], "B": ["rice"]})

    def test_within_a_split_an_item_moves_to_the_dearer_store_when_that_removes_a_surcharge(self):
        # Each store alone lacks something, so both are used. Yoghurt costs 20 more at B, and B's basket of rice alone would pay 500 to reach its minimum.
        wants = ["coffee", "yoghurt", "rice"]
        a = store("A", {"coffee": 3000, "yoghurt": 500}, delivery=200)
        b = store("B", {"yoghurt": 520, "rice": 600}, delivery=200, minimum=1100)
        best = solver.plans(wants, [a, b])[0]
        self.assertEqual(shape(best), {"A": ["coffee"], "B": ["rice", "yoghurt"]})
        self.assertEqual(best["total"], 3000 + 200 + 520 + 600 + 200)

    def test_fuller_coverage_outranks_a_cheaper_partial_plan(self):
        wants = ["milk", "rice"]
        cheap_partial = store("A", {"milk": 100}, delivery=0)
        full = store("B", {"milk": 900, "rice": 900}, delivery=900)
        ranked = solver.plans(wants, [cheap_partial, full], max_stores=1)
        self.assertEqual(shape(ranked[0]), {"B": ["milk", "rice"]})
        self.assertEqual(ranked[1]["missing"], ["rice"])

    def test_a_split_that_neither_saves_nor_covers_more_is_not_listed(self):
        wants = ["milk", "eggs"]
        a = store("A", {"milk": 500, "eggs": 500}, delivery=200)
        b = store("B", {"milk": 500, "eggs": 500}, delivery=200)
        ranked = solver.plans(wants, [a, b])
        self.assertTrue(all(len(plan["baskets"]) == 1 for plan in ranked))

    def test_three_stores_are_used_only_when_allowed(self):
        wants = ["a", "b", "c"]
        stores = [store("A", {"a": 100}), store("B", {"b": 100}), store("C", {"c": 100})]
        self.assertEqual(len(solver.plans(wants, stores, max_stores=2)[0]["missing"]), 1)
        self.assertEqual(solver.plans(wants, stores, max_stores=3)[0]["missing"], [])

    def test_an_offer_above_a_threshold_draws_the_list_into_one_store(self):
        offer = {"label": "Offer", "segments": [[3000, None, -1000, 0]]}
        a = store("A", {"x": 1600, "y": 1600}, delivery=100, extra_fees=[offer])
        b = store("B", {"x": 1500, "y": 1500}, delivery=100)
        best = solver.plans(["x", "y"], [a, b])[0]
        self.assertEqual(shape(best), {"A": ["x", "y"]})
        self.assertEqual(best["total"], 3200 - 1000 + 100)

    def test_a_surcharge_reckoned_on_listed_prices_spares_a_discounted_basket(self):
        s = store("A", {"milk": (2196, 2500)}, delivery=159, minimum=2500)
        s["fees"][1]["on"] = "list"
        self.assertEqual(solver.plans(["milk"], [s])[0]["total"], 2196 + 159)


class Exactness(unittest.TestCase):
    """The search against a plain enumeration of every division."""

    def brute(self, wants, stores, size):
        best = None
        for group in combinations(stores, size):
            holders = [[i for i, s in enumerate(group) if want in s["lines"]] for want in wants]
            covered = [want for want, held in zip(wants, holders) if held]
            for placing in product(*[held for held in holders if held]):
                if len(set(placing)) < size:
                    continue
                paid, listed = [0] * size, [0] * size
                for want, i in zip(covered, placing):
                    paid[i] += group[i]["lines"][want][0]
                    listed[i] += group[i]["lines"][want][1]
                cost = sum(paid) + sum(solver.fee_total(group[i], paid[i], listed[i]) for i in range(size))
                key = (len(wants) - len(covered), cost)
                best = key if best is None or key < best else best
        return best

    def test_random_lists_match_the_enumeration(self):
        rng = random.Random(20261127)
        for _ in range(250):
            wants = [f"w{i}" for i in range(rng.randint(1, 7))]
            stores = []
            for ref in "ABCD"[: rng.randint(1, 4)]:
                minimum = rng.choice([0, 1500, 2500, 4000])
                fees = [{"label": "Delivery", "segments": [[0, None, rng.randint(0, 700), 0]]},
                        {"label": "Service", "segments": [[0, 1250, 100, 0], [1250, 6238, 0, 0.08], [6238, None, 499, 0]]}]
                if minimum:
                    cap = rng.choice([399, minimum])
                    fees.append({"label": "Small order", "on": rng.choice(["list", "paid"]),
                                 "segments": [[0, minimum - cap, cap, 0], [minimum - cap, minimum, minimum, -1]]})
                if rng.random() < 0.4:
                    fees.append({"label": "Offer", "segments": [[rng.choice([2000, 5000]), None, -rng.choice([300, 1200]), -rng.choice([0, 0.1])]]})
                lines = {}
                for want in wants:
                    if rng.random() < 0.75:
                        paid = rng.randint(100, 2500)
                        lines[want] = (paid, paid + rng.choice([0, 0, 250]))
                if lines:
                    stores.append({"ref": ref, "fees": fees, "lines": lines})
            for size in (1, 2, 3):
                if len(stores) < size:
                    continue
                expected = min((found for found in (self.brute(wants, stores, n) for n in range(1, size + 1)) if found), default=None)
                ranked = solver.plans(wants, stores, max_stores=size)
                got = (len(ranked[0]["missing"]), ranked[0]["total"]) if ranked else None
                self.assertEqual(got, expected)

    def test_a_long_list_is_solved_exactly_and_not_marked_approximate(self):
        rng = random.Random(7)
        wants = [f"w{i}" for i in range(30)]
        a = store("A", {want: rng.randint(200, 900) for want in wants}, delivery=300, minimum=2500)
        b = store("B", {want: rng.randint(200, 900) for want in wants}, delivery=300, minimum=2500)
        best = solver.plans(wants, [a, b])[0]
        self.assertFalse(best["approximate"])
        cheapest_shelves = sum(min(a["lines"][want][0], b["lines"][want][0]) for want in wants)
        self.assertEqual(best["total"], cheapest_shelves + 600)


class NextThreshold(unittest.TestCase):
    def test_a_surcharge_gap_is_reported_with_what_it_saves(self):
        s = store("A", {}, delivery=200, minimum=2500)
        self.assertEqual(solver.next_threshold(s, 2180), (320, 320))

    def test_nothing_to_report_above_every_threshold(self):
        s = store("A", {}, delivery=200, minimum=2500)
        self.assertIsNone(solver.next_threshold(s, 2600))

    def test_free_delivery_within_reach_is_reported(self):
        s = {"ref": "A", "fees": [{"label": "Delivery", "segments": [[0, 4000, 399, 0]]}], "lines": {}}
        self.assertEqual(solver.next_threshold(s, 3500), (500, 399))

    def test_a_threshold_that_returns_little_of_the_extra_spend_is_not_reported(self):
        s = {"ref": "A", "fees": [{"label": "Delivery", "segments": [[0, 4000, 399, 0]]}], "lines": {}}
        self.assertIsNone(solver.next_threshold(s, 1000))
        growing = {"ref": "A", "fees": [{"label": "Offer", "segments": [[5000, 20000, 0, -0.1], [20000, None, -2000, 0]]}], "lines": {}}
        self.assertIsNone(solver.next_threshold(growing, 8600))

    def test_the_gap_is_measured_on_the_value_the_fee_looks_at(self):
        s = store("A", {}, minimum=2500)
        s["fees"][1]["on"] = "list"
        self.assertEqual(solver.next_threshold(s, 2000, 2300), (200, 200))


if __name__ == "__main__":
    unittest.main()
