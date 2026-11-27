"""Fee rules of the platform adapters, against what the platforms charged or published on 2026-11-27 in Tbilisi."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import glovo  # noqa: E402
import solver  # noqa: E402
import wolt  # noqa: E402


def amounts(fees, subtotal):
    return {fee["label"]: solver.fee_amount(fee["segments"], subtotal) for fee in fees}


class WoltSchedule(unittest.TestCase):
    """Each table row is (subtotal, small order fee, service fee) as Wolt's checkout priced it."""

    def test_grocery_store_matches_the_measured_checkout(self):
        ranges = [{"min": 0, "max": 1250, "a": 1350, "b": -1.0}, {"min": 1250, "max": 6238, "a": 0, "b": 0.08}, {"min": 6238, "max": 0, "a": 499, "b": 0.0}]
        fees = wolt.schedule(2500, ranges, {"delivery": 259, "small_order": 399, "bag": 40})
        measured = [
            (300, 399, 100), (500, 399, 100), (1000, 399, 100), (1200, 399, 100), (1250, 399, 100), (1300, 399, 104),
            (1500, 399, 120), (2000, 399, 160), (2400, 100, 192), (2450, 50, 196), (2500, 0, 200), (2600, 0, 208),
            (4000, 0, 320), (6200, 0, 496), (6300, 0, 499), (7000, 0, 499), (12000, 0, 499),
        ]
        for subtotal, small_order, service in measured:
            with self.subTest(subtotal=subtotal):
                self.assertEqual(amounts(fees, subtotal), {"Delivery": 259, "Service fee": service, "Small order fee": small_order, "Bag": 40})

    def test_restaurant_matches_the_measured_checkout(self):
        ranges = [{"min": 0, "max": 1200, "a": 1300, "b": -1.0}, {"min": 1200, "max": 1250, "a": 100, "b": 0.0},
                  {"min": 1250, "max": 6238, "a": 0, "b": 0.08}, {"min": 6238, "max": 0, "a": 499, "b": 0.0}]
        fees = wolt.schedule(1200, ranges, {"delivery": 129, "small_order": 299, "bag": 0})
        measured = [(1, 299, 100), (600, 299, 100), (1100, 100, 100), (1200, 0, 100), (1250, 0, 100), (3000, 0, 240), (9000, 0, 499)]
        for subtotal, small_order, service in measured:
            with self.subTest(subtotal=subtotal):
                self.assertEqual(amounts(fees, subtotal), {"Delivery": 129, "Service fee": service, "Small order fee": small_order})

    def test_surcharge_without_a_cap_tops_up_to_the_minimum(self):
        fees = wolt.schedule(1200, [], {"delivery": 100, "small_order": 1199, "bag": 0})
        self.assertEqual(amounts(fees, 200)["Small order fee"], 1000)


class GlovoSchedule(unittest.TestCase):
    """The published numbers of one supermarket; the amounts follow this project's reading of them, which Glovo has not confirmed."""

    def setUp(self):
        self.fees = glovo.schedule(
            1.49,
            {"minValue": 229, "maxValue": 699, "setupValue": 9},
            [{"lowerBound": 0.0, "upperBound": 30.0, "surchargeInfo": {"amount": 2.99}, "surchargeStrategy": "CAPPED"}],
        )

    def test_service_fee_is_a_share_between_its_bounds(self):
        self.assertEqual(amounts(self.fees, 1000)["Service fee"], 229)
        self.assertEqual(amounts(self.fees, 5000)["Service fee"], 450)
        self.assertEqual(amounts(self.fees, 20000)["Service fee"], 699)

    def test_capped_surcharge_shrinks_to_the_gap_near_the_threshold(self):
        self.assertEqual(amounts(self.fees, 1000)["Small order fee"], 299)
        self.assertEqual(amounts(self.fees, 2900)["Small order fee"], 100)
        self.assertEqual(amounts(self.fees, 3000)["Small order fee"], 0)

    def test_delivery_is_flat(self):
        self.assertEqual(amounts(self.fees, 100)["Delivery"], 149)
        self.assertEqual(amounts(self.fees, 90000)["Delivery"], 149)


if __name__ == "__main__":
    unittest.main()
