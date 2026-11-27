import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import solver  # noqa: E402

def store(ref, prices, delivery=0, minimum=0):
    """A store with a flat delivery price and a surcharge topping baskets up to `minimum`."""
    fees = [{"label": "Delivery", "segments": [[0, None, delivery, 0]]}]
    if minimum:
        fees.append({"label": "Small order", "segments": [[0, minimum, minimum, -1]]})
    return {"ref": ref, "fees": fees, "prices": prices}


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


class Plans(unittest.TestCase):
    def test_one_store_with_everything_beats_a_split_that_pays_two_sets_of_fees(self):
        wants = ["milk", "eggs", "bread", "rice", "spice"]
        everything = store("A", {"milk": 550, "eggs": 590, "bread": 250, "rice": 700, "spice": 450}, delivery=260, minimum=2500)
        cheaper_rice = store("B", {"rice": 600}, delivery=260, minimum=2500)
        best = solver.plans(wants, [everything, cheaper_rice])[0]
        self.assertEqual(shape(best), {"A": sorted(wants)})
        self.assertEqual(best["missing"], [])
        self.assertEqual(best["total"], 2540 + 260)

    def test_split_is_chosen_when_no_store_has_everything(self):
        wants = ["milk", "eggs", "bread", "rice", "spice"]
        no_rice = store("A", {"milk": 550, "eggs": 590, "bread": 250, "spice": 450}, delivery=260, minimum=2500)
        has_rice = store("B", {"rice": 700, "milk": 600, "eggs": 640}, delivery=260, minimum=2500)
        best = solver.plans(wants, [no_rice, has_rice])[0]
        self.assertEqual(best["missing"], [])
        self.assertEqual(set(shape(best)), {"A", "B"})

    def test_items_move_to_the_dearer_store_when_that_removes_a_surcharge(self):
        # Rice exists only at B, so B's basket is tiny and pays a surcharge up to its minimum. Moving the expensive item there costs 20 more on the shelf and removes far more in surcharge.
        wants = ["rice", "coffee", "milk"]
        a = store("A", {"coffee": 2000, "milk": 500}, delivery=200, minimum=0)
        b = store("B", {"rice": 600, "coffee": 2020, "milk": 520}, delivery=200, minimum=2500)
        ranked = solver.plans(wants, [a, b])
        best = ranked[0]
        self.assertEqual(best["missing"], [])
        self.assertEqual(shape(best), {"B": ["coffee", "milk", "rice"]})
        self.assertEqual(best["total"], 600 + 2020 + 520 + 200)

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

    def test_large_lists_are_marked_approximate_and_still_cover_everything(self):
        wants = [f"w{i}" for i in range(20)]
        a = store("A", {w: 100 + i for i, w in enumerate(wants)}, delivery=200, minimum=2500)
        b = store("B", {w: 120 - i for i, w in enumerate(wants)}, delivery=200, minimum=2500)
        ranked = solver.plans(wants, [a, b])
        self.assertEqual(ranked[0]["missing"], [])
        pair = [plan for plan in ranked if len(plan["baskets"]) == 2]
        self.assertTrue(all(plan["approximate"] for plan in pair))


class NextThreshold(unittest.TestCase):
    def test_surcharge_gap_is_reported_with_what_it_saves(self):
        s = store("A", {}, delivery=200, minimum=2500)
        self.assertEqual(solver.next_threshold(s, 2180), (320, 320))

    def test_nothing_to_report_above_every_threshold(self):
        s = store("A", {}, delivery=200, minimum=2500)
        self.assertIsNone(solver.next_threshold(s, 2600))

    def test_free_delivery_threshold(self):
        s = {"ref": "A", "fees": [{"label": "Delivery", "segments": [[0, 4000, 399, 0]]}], "prices": {}}
        self.assertEqual(solver.next_threshold(s, 3500), (500, 399))


if __name__ == "__main__":
    unittest.main()
