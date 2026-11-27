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


class WoltOffers(unittest.TestCase):
    """Two offers open to every customer, with the discounts Wolt's checkout gave for them."""

    def offer(self, goods, least, **conditions):
        return {"effects": {"basket_discount": goods}, "conditions": {"basket_contains": [{"min_amount": least}], **conditions},
                "description": {"title": "", "points": []}}

    def test_a_percentage_with_a_cap_matches_the_measured_checkout(self):
        segments = wolt.offer_segments(self.offer({"amount": 0, "fraction": 0.1, "max_amount": 2000}, 5000), 59)
        self.assertEqual([solver.fee_amount(segments, subtotal) for subtotal in (4000, 6000, 30000)], [0, -600, -2000])

    def test_a_fixed_amount_matches_the_measured_checkout(self):
        segments = wolt.offer_segments(self.offer({"amount": 5000, "fraction": None, "max_amount": None}, 20000), 99)
        self.assertEqual([solver.fee_amount(segments, subtotal) for subtotal in (15000, 25000)], [0, -5000])

    def test_an_offer_tied_to_more_than_basket_size_is_left_to_the_pricing(self):
        self.assertIsNone(wolt.offer_segments(self.offer({"amount": 500}, 0, weekly_time_restrictions=[{"day": 1}]), 99))
        self.assertIsNone(wolt.offer_segments(self.offer({"amount": 500}, 0, delivery_methods=["takeaway"]), 99))

    def test_free_delivery_above_a_minimum_takes_off_the_delivery_price(self):
        offer = {"effects": {"delivery_discount": {"amount": 0, "fraction": 1.0}}, "conditions": {"basket_contains": [{"min_amount": 4000}]},
                 "description": {"title": "", "points": []}}
        self.assertEqual([solver.fee_amount(wolt.offer_segments(offer, 259), subtotal) for subtotal in (3999, 4000)], [0, -259])

    def test_the_audience_is_read_from_the_condition_or_the_wording(self):
        offer = self.offer({"amount": 1200}, 3000)
        self.assertIsNone(wolt.audience(offer))
        offer["description"]["points"] = ["GEL30 minimum order", "For new users with a local phone number."]
        self.assertEqual(wolt.audience(offer), "new customers")
        self.assertEqual(wolt.audience(self.offer({"amount": 1}, 0, has_wolt_plus=True)), "Wolt+ members")


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
