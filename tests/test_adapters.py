"""Each platform's reader against replies cut down from real ones (Tbilisi, 2026-11-27)."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import bolt  # noqa: E402
import glovo  # noqa: E402
import wolt  # noqa: E402

POINT = (41.6938, 44.8015)


def answering(table):
    """A stand-in for fetch: the reply whose key occurs in the URL, called with the request body when it is a function."""
    def fetch(url, headers=None, body=None, timeout=40):
        for part, reply in table.items():
            if part in url:
                return reply(body) if callable(reply) else reply
        raise AssertionError(f"unexpected call to {url}")
    return fetch


class WoltShelf(unittest.TestCase):
    STORE = {"key": "market", "item_offers": {"shampoo": [0.3, 1], "franui": [0.3, 2]}}
    REPLY = {
        "options": [{"id": "flavours", "values": [{"id": "v1", "name": "Four cheese", "price": 1500}, {"id": "v2", "name": "Spinach", "price": 1300}]},
                    {"id": "extras", "values": [{"id": "v3", "name": "Sauce", "price": 200}]}],
        "items": [
            {"id": "milk", "name": "Sante Milk 2.5%, 1L", "price": 549, "original_price": 625, "unit_info": "1 l", "purchasable_balance": 37},
            {"id": "shampoo", "name": "Bioderma Node 400მლ", "price": 8795, "purchasable_balance": 5},
            {"id": "franui", "name": "Franui 150g", "price": 2450, "purchasable_balance": 9},
            {"id": "cheese", "name": "Cheese Imeruli 1 kg", "price": 2200, "purchasable_balance": 9000,
             "sell_by_weight_config": {"grams_per_step": 500, "price_per_kg": 2200}},
            {"id": "set", "name": "Khachapuri set", "price": 200, "options": [
                {"id": "b1", "option_id": "flavours", "multi_choice_config": {"total_range": {"min": 3, "max": 100}, "max_single_selections": 100}},
                {"id": "b2", "option_id": "extras", "multi_choice_config": {"total_range": {"min": 0, "max": 2}}}]},
            {"id": "gone", "name": "Sold out", "price": 100, "purchasable_balance": 0},
            {"id": "off", "name": "Not sold now", "price": 100, "disabled_info": {"reason": "hours"}},
        ],
    }

    def setUp(self):
        with mock.patch.object(wolt, "fetch", answering({"items/search": self.REPLY})):
            self.offers = {offer["id"]: offer for offer in wolt.shelf(self.STORE, "anything", *POINT)}

    def test_what_cannot_be_bought_now_is_left_out(self):
        self.assertEqual(list(self.offers), ["milk", "shampoo", "franui", "cheese", "set"])

    def test_a_price_cut_keeps_the_old_price_as_the_listed_one(self):
        self.assertEqual({k: self.offers["milk"][k] for k in ("price", "list", "base", "size")}, {"price": 549, "list": 625, "base": 549, "size": [1000, "ml"]})

    def test_a_campaign_on_one_unit_is_taken_off_the_shelf_price(self):
        shampoo = self.offers["shampoo"]
        self.assertEqual((shampoo["price"], shampoo["list"], shampoo["base"]), (6156, 8795, 8795))

    def test_a_campaign_needing_several_units_is_kept_as_a_condition(self):
        self.assertEqual((self.offers["franui"]["price"], self.offers["franui"]["bulk"]), (2450, [2, 0.3]))

    def test_goods_by_weight_are_priced_by_the_step(self):
        cheese = self.offers["cheese"]
        self.assertEqual((cheese["price"], cheese["size"], cheese["weighed"], cheese["stock"]), (1100, [500, "g"], True, None))

    def test_a_dish_starts_at_its_cheapest_obligatory_choices(self):
        dish = self.offers["set"]
        self.assertEqual((dish["price"], dish["base"], dish["extra"], dish["from"]), (4100, 200, 3900, True))
        self.assertEqual(dish["choices"], [{"id": "b1", "values": [{"id": "v2", "count": 3, "price": 1300}]}])


class WoltPricing(unittest.TestCase):
    STORE = {"venue_id": "v", "currency": "GEL", "country": "GEO", "offer_ids": ["c1"]}

    def row(self, label, amount, original=None):
        return {"template": "amount_row", "label": label, "amount": {"amount": amount}, "original_amount": {"amount": original} if original else None}

    def test_goods_fees_and_offers_are_read_up_to_the_total(self):
        rows = [{"template": "fees_explanation_row"}, self.row("Item subtotal", 3430, 4900), self.row("Service fee", 274), self.row("Delivery (610 m)", 159),
                {"template": "price_total_amount_row", "label": "Total", "price_total_amount": {"amount": 3863}},
                self.row("Applied offers", 0), {"template": "discount_row", "label": "Buy Any 2x Franui & Get 30% OFF"}]
        sent = {}
        with mock.patch.object(wolt, "fetch", answering({"pages/checkout": lambda body: sent.update(body) or {"checkout_rows": rows}})):
            priced = wolt.quote(self.STORE, [({"id": "franui", "base": 2450, "price": 2450}, 2)], *POINT)
        self.assertEqual(priced, {"goods": 3430, "fees": [("Service fee", 274), ("Delivery (610 m)", 159)], "offers": ["Buy Any 2x Franui & Get 30% OFF"]})
        plan = sent["purchase_plan"]
        self.assertEqual(plan["use_promo_discount_ids"], ["c1"])
        self.assertEqual({k: plan["menu_items"][0][k] for k in ("id", "count", "base_price", "end_amount")}, {"id": "franui", "count": 2, "base_price": 2450, "end_amount": 4900})

    def test_choices_and_weighed_goods_are_stated_as_checkout_wants_them(self):
        sent = {}
        lines = [({"id": "set", "base": 200, "extra": 3900, "choices": [{"id": "b1", "values": []}]}, 1), ({"id": "cheese", "base": 1100, "weighed": True}, 2)]
        with mock.patch.object(wolt, "fetch", answering({"pages/checkout": lambda body: sent.update(body) or {"checkout_rows": []}})):
            wolt.quote(self.STORE, lines, *POINT)
        dish, cheese = sent["purchase_plan"]["menu_items"]
        self.assertEqual((dish["base_price"], dish["end_amount"], dish["options"]), (200, 4100, [{"id": "b1", "values": []}]))
        self.assertEqual((cheese["count"], cheese["end_amount"], cheese["is_weighted_item"]), (1, 2200, True))


class WoltStore(unittest.TestCase):
    def campaign(self, title, effects, conditions=None, points=()):
        return {"id": title, "effects": effects, "conditions": conditions or {}, "description": {"title": title, "points": list(points)}}

    def test_a_store_is_assembled_from_its_three_calls(self):
        campaigns = [
            self.campaign("30% off shampoo", {"item_discount": {"fraction": 0.3, "include": {"items": ["shampoo"]}}}),
            self.campaign("2x Franui", {"item_discount": {"fraction": 0.3, "include": {"items": ["franui"]}}}, {"basket_contains": [{"min_quantity": 2}]}),
            self.campaign("GEL10 off on orders over GEL60", {"basket_discount": {"amount": 1000}}, {"basket_contains": [{"min_amount": 6000}]}),
            self.campaign("GEL0 delivery fee", {"delivery_discount": {"fraction": 1.0}}, points=["For new users with a local phone number."]),
        ]
        dynamic = {"venue": {"delivery_open_status": {"is_open": True}, "online": True, "open_status": {"value": "Open until 23:00"},
                             "delivery_configs": [{"schedule": "standard", "estimate": {"label": "30-40 min"}}]},
                   "venue_raw": {"discounts": campaigns, "delivery_specs": {"order_minimum_no_surcharge": 2500, "delivery_pricing": {"price_ranges": [
                       {"min": 0, "max": 1250, "a": 1350, "b": -1.0}, {"min": 1250, "max": 6238, "a": 0, "b": 0.08}, {"min": 6238, "max": 0, "a": 499, "b": 0.0}]}}}}
        static = {"venue": {"name": " Market ", "share_url": "https://wolt.com/x", "currency": "GEL", "id": "v", "country": "GEO", "rating": {"score": "9.4"}}}
        probe = {"checkout_rows": [{"template": "amount_row", "label": "Delivery (610 m)", "amount": {"amount": 259}}],
                 "telemetry": {"delivery_price": 259, "small_order_fee": 399}, "purchase_validation": {"bag_fee": 40}}
        sent = {}
        table = {"/static": static, "/dynamic/": dynamic, "pages/checkout": lambda body: sent.update(body) or probe}
        with mock.patch.object(wolt, "fetch", answering(table)):
            record = wolt.store("market", *POINT)
        self.assertEqual((record["name"], record["open"], record["eta"], record["distance"], record["rating"]), ("Market", True, "30-40 min", "610 m", "9.4"))
        self.assertEqual(record["offer_ids"], ["30% off shampoo", "2x Franui", "GEL10 off on orders over GEL60"])
        self.assertEqual(sent["purchase_plan"]["use_promo_discount_ids"], record["offer_ids"])
        self.assertEqual(record["item_offers"], {"shampoo": [0.3, 1], "franui": [0.3, 2]})
        self.assertEqual([fee["label"] for fee in record["fees"]], ["Delivery", "Service fee", "Small order fee", "Bag", "Offer: GEL10 off on orders over GEL60"])
        self.assertEqual(record["fees"][2]["on"], "list")
        self.assertIn("offer: GEL10 off on orders over GEL60 (counted in the totals)", record["notes"])
        self.assertIn("offer: GEL0 delivery fee (new customers; not counted)", record["notes"])

    def test_the_search_tells_stores_from_restaurants_and_leaves_open_unknown(self):
        def hit(slug, line, available=True):
            return {"link": {"menu_item_details": {"venue_slug": slug, "venue_name": slug.title(), "product_line": line, "price": 500}},
                    "menu_item": {"is_available": available}}
        reply = {"sections": [{"items": [hit("spar", "grocery"), hit("gpc", "pharmacy"), hit("grill", "restaurant"), hit("gone", "grocery", False)]}]}
        with mock.patch.object(wolt, "fetch", answering({"pages/search": reply})):
            stores = [hit_["store"] for hit_ in wolt.discover("x", *POINT, False)]
            dishes = wolt.discover("x", *POINT, True)
        self.assertEqual(stores, ["spar", "gpc"])
        self.assertEqual(dishes, [{"store": "grill", "name": "Grill", "open": None, "price": 500}])


class BoltShelf(unittest.TestCase):
    def dish(self, ident, name, price, score, **extra):
        return {"type": "dish", "id": ident, "name": {"value": name}, "price": {"value": price}, "availability": "in_stock", "score": score,
                "option_group_presence": "none", **extra}

    def test_packs_are_priced_as_named_and_sized_from_the_price_per_kilogram(self):
        items = {
            "1": self.dish(1, "Cheese / Frico / Gouda briquette 100 g", 4.5, 50, selling_unit="kg", unit_price={"unit_price": {"value": "45,00 ₾/kg"}}),
            "2": self.dish(2, "Butter Valio 500 gr", 36.95, 70, selling_unit="piece"),
            "3": self.dish(3, "Shawarma", 15.0, 60, option_group_presence="required"),
            "4": {"type": "category", "id": 4},
            "5": self.dish(5, "Out", 1.0, 99, availability="out_of_stock"),
        }
        with mock.patch.object(bolt, "fetch", answering({"searchInMenu": {"code": 0, "data": {"items": items}}})):
            offers = bolt.shelf({"key": "99610"}, "x", *POINT)
        self.assertEqual([offer["name"] for offer in offers], ["Butter Valio 500 gr", "Shawarma", "Cheese / Frico / Gouda briquette 100 g"])
        self.assertEqual([(offer["price"], offer["size"], offer["from"]) for offer in offers],
                         [(3695, [500, "g"], False), (1500, None, True), (450, [100, "g"], False)])

    def test_a_refused_call_is_an_error_naming_it(self):
        with mock.patch.object(bolt, "fetch", answering({"searchInMenu": {"code": 702, "message": "INVALID_REQUEST"}})):
            with self.assertRaisesRegex(RuntimeError, "Bolt searchInMenu: INVALID_REQUEST"):
                bolt.shelf({"key": "1"}, "x", *POINT)

    def test_the_search_previews_what_matched_in_each_provider(self):
        providers = [{"id": 7, "name": " GPC ", "availability": {"delivery": {"instant": True}}}, {"id": 8, "name": "Closed", "availability": {"delivery": {"instant": False}}}]
        sent = {}
        table = {"deliverySearch": lambda body: sent.update(search=body) or {"code": 0, "data": {"providers": providers}},
                 "getProviderPreviewMenuItems": {"code": 0, "data": {"preview_items": {"7": {"items": {"a": {"price": {"value": 4.18}}}}, "8": {"items": {}}}}}}
        with mock.patch.object(bolt, "fetch", answering(table)):
            hits = bolt.discover("paracetamol", *POINT, False)
        self.assertEqual(hits, [{"store": "7", "name": "GPC", "open": True, "price": 418}])
        self.assertEqual(sent["search"]["search_tab_id"], "stores")


class Glovo(unittest.TestCase):
    PLACE = {"cityCode": "TBI", "countryCode": "GE", "addressComponents": {"administrative_area_level_1": "Tbilisi"}}

    def card(self, slug, category, is_open="true"):
        return {"type": "STORE_CARD_V2", "data": {"slug": slug, "title": {"text": {"text": slug.upper()}}},
                "actions": [{"data": {"events": [{"data": {"shopIsOpen": is_open, "glovoCategoryId": category}}]}}]}

    def row(self, *prices):
        return {"type": "CAROUSEL", "data": {"elements": [{"data": {"pricing": {"finalPrice": price}}} for price in prices]}}

    def search(self, food):
        elements = [{"type": "DISCLAIMERS", "data": {}}, self.card("spar", "4"), self.row("4,49 ₾", "5,60 ₾"), self.card("cafe", "1"), self.row("14,00 ₾"),
                    self.card("night", "4", "false"), self.row("3,00 ₾"), self.card("nameonly", "4")]
        table = {"addresslookup": self.PLACE, "store_wall/search": {"data": {"body": {"data": {"elements": elements}}}}}
        with mock.patch.object(glovo, "fetch", answering(table)), mock.patch.dict(glovo._places, clear=True):
            return glovo.discover("milk", *POINT, food)

    def test_the_search_screen_is_read_card_by_card(self):
        self.assertEqual(self.search(False), [
            {"store": "spar", "name": "SPAR", "open": True, "price": 449}, {"store": "spar", "name": "SPAR", "open": True, "price": 560},
            {"store": "night", "name": "NIGHT", "open": False, "price": 300}])
        self.assertEqual(self.search(True), [{"store": "cafe", "name": "CAFE", "open": True, "price": 1400}])

    def test_a_card_without_the_store_s_state_stops_the_search_with_its_name(self):
        elements = [{"type": "STORE_CARD_V2", "data": {"slug": "odd"}}]
        table = {"addresslookup": self.PLACE, "store_wall/search": {"data": {"body": {"data": {"elements": elements}}}}}
        with mock.patch.object(glovo, "fetch", answering(table)), mock.patch.dict(glovo._places, clear=True):
            with self.assertRaisesRegex(RuntimeError, "odd"):
                glovo.discover("milk", *POINT, False)

    def test_a_shelf_carries_promotions_sizes_and_choices(self):
        products = [
            {"id": 1, "name": "რძე /სოფლის ნობათი/ 2,5% 950მლ", "price": 6.2, "promotion": {"price": 5.49, "title": "-0,71 ₾", "isPrime": False}},
            {"id": 2, "name": "პიცა", "price": 30.0, "promotion": {"price": 18.0, "title": "-40%", "isPrime": True}, "attributeGroups": [{"id": 1}]},
            {"id": 3, "name": "კვერცხი 10ც", "price": 5.8, "description": " fresh "},
        ]
        table = {"addresslookup": self.PLACE, "/search?query=": {"results": [{"products": products}]}}
        with mock.patch.object(glovo, "fetch", answering(table)), mock.patch.dict(glovo._places, clear=True):
            milk, pizza, eggs = glovo.shelf({"store_id": 1, "address_id": 2}, "x", *POINT)
        self.assertEqual((milk["price"], milk["list"], milk["size"]), (549, 620, [950, "ml"]))
        self.assertEqual((pizza["price"], pizza["from"], pizza["note"]), (3000, True, "offer: -40% (Prime members)"))
        self.assertEqual((eggs["size"], eggs["note"]), ([10, "pc"], "fresh"))

    def test_a_store_counts_a_whole_menu_offer_and_lists_the_rest(self):
        info = {"id": 26609, "addressId": 687129, "name": "Gennaro", "slug": "gennaro-tbi", "open": True, "rating": "97%", "distance": "4km",
                "deliveryFeeInfo": {"fee": 5.99}, "serviceFeeInfo": {"minValue": 129, "maxValue": 499, "setupValue": 9}, "primeAvailable": True,
                "promotions": [{"title": "Free delivery on the first order", "type": "FREE_DELIVERY", "description": ""},
                               {"title": "-20%", "type": "BASKET_PERCENTAGE", "description": "whole menu", "minimumBasketSizeCents": 4000, "percentage": 20.0},
                               {"title": "-25%", "type": "BASKET_PERCENTAGE", "description": "whole menu", "minimumBasketSizeCents": 4000, "percentage": 25.0, "prime": True}]}
        ranges = [{"lowerBound": 0.0, "upperBound": 15.0, "upperBoundInfo": {"currencyCode": "GEL"}, "surchargeInfo": {"amount": 1.99}, "surchargeStrategy": "CAPPED"}]
        table = {"addresslookup": self.PLACE, "/v3/stores/gennaro-tbi": info, "node/store_fees": {"data": {"ranges": ranges}}}
        with mock.patch.object(glovo, "fetch", answering(table)), mock.patch.dict(glovo._places, clear=True):
            record = glovo.store("gennaro-tbi", *POINT)
        self.assertEqual(record["url"], "https://glovoapp.com/en/ge/tbilisi/stores/gennaro-tbi")
        self.assertEqual([fee["label"] for fee in record["fees"]], ["Delivery", "Service fee", "Small order fee", "Offer: -20% whole menu, baskets from 40.00"])
        self.assertEqual(record["fees"][3]["segments"], [[4000, None, 0, -0.2]])
        self.assertEqual(record["notes"][:3], ["offer: Free delivery on the first order", "offer: -20% whole menu, baskets from 40.00 (counted in the totals)",
                                               "offer: -25% whole menu, baskets from 40.00 (Prime members)"])
        self.assertEqual((record["currency"], record["distance"], record["open"]), ("GEL", "4km", True))


if __name__ == "__main__":
    unittest.main()
