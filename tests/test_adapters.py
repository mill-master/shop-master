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
    def fetch(url, headers=None, body=None, form=None, timeout=40, acting=False):
        for part, reply in table.items():
            if part in url:
                return reply(body) if callable(reply) else reply
        raise AssertionError(f"unexpected call to {url}")
    return fetch


def cut(fraction=None, units=1, amount=None, base_only=False):
    """A store campaign on products as the Wolt reader keeps it."""
    return {"fraction": fraction, "amount": amount, "base_only": base_only, "units": units}


class WoltShelf(unittest.TestCase):
    STORE = {"key": "market", "scale": 1, "item_offers": {"shampoo": cut(0.3), "franui": cut(0.3, units=2), "razor": cut(amount=300), "set": cut(0.32, base_only=True)},
             "category_offers": {"sweets": cut(0.3)}}
    REPLY = {
        "categories": [{"id": "dairy", "item_ids": ["milk"]}, {"id": "all", "item_ids": ["wafer"]}, {"id": "sweets", "item_ids": ["wafer"]}],
        "options": [{"id": "flavours", "values": [{"id": "v1", "name": "Four cheese", "price": 1500}, {"id": "v2", "name": "Spinach", "price": 1300}]},
                    {"id": "extras", "values": [{"id": "v3", "name": "Sauce", "price": 200}]}],
        "items": [
            {"id": "milk", "name": "Sante Milk 2.5%, 1L", "price": 549, "original_price": 625, "unit_info": "1 l", "purchasable_balance": 37},
            {"id": "shampoo", "name": "Bioderma Node 400მლ", "price": 8795, "purchasable_balance": 5, "max_quantity_per_purchase": 3},
            {"id": "wafer", "name": "ROSHEN Lakmi 90 g", "price": 199, "original_price": 395},
            {"id": "razor", "name": "Razor", "price": 1500},
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
        self.assertEqual(list(self.offers), ["milk", "shampoo", "wafer", "razor", "franui", "cheese", "set"])

    def test_a_price_cut_keeps_the_old_price_as_the_listed_one(self):
        self.assertEqual({k: self.offers["milk"][k] for k in ("price", "list", "base", "size")}, {"price": 549, "list": 625, "base": 549, "size": [1000, "ml"]})

    def test_a_campaign_on_one_unit_is_taken_off_the_shelf_price(self):
        shampoo = self.offers["shampoo"]
        self.assertEqual((shampoo["price"], shampoo["list"], shampoo["base"], shampoo["limit"]), (6156, 8795, 8795, 3))

    def test_a_campaign_on_a_shelf_category_reaches_the_products_on_it(self):
        # Measured at Carrefour Vekua: listed at 1.99 after a cut from 3.95, charged 1.39 under a 30% campaign on its category.
        wafer = self.offers["wafer"]
        self.assertEqual((wafer["price"], wafer["list"], wafer["category"]), (139, 395, "sweets"))
        self.assertEqual(self.offers["milk"]["category"], "dairy")

    def test_a_campaign_of_a_fixed_amount_comes_off_each_unit(self):
        self.assertEqual(self.offers["razor"]["price"], 1200)

    def test_a_campaign_needing_several_units_is_kept_as_a_condition(self):
        self.assertEqual((self.offers["franui"]["price"], self.offers["franui"]["bulk"]), (2450, [2, 735]))

    def test_goods_by_weight_are_priced_by_the_step(self):
        cheese = self.offers["cheese"]
        self.assertEqual((cheese["price"], cheese["size"], cheese["weighed"], cheese["stock"]), (1100, [500, "g"], True, None))

    def test_a_dish_starts_at_its_cheapest_obligatory_choices(self):
        dish = self.offers["set"]
        # Its campaign spares the choices: 32% comes off the dish's own 2.00 and nothing off the 39.00 of choices.
        self.assertEqual((dish["price"], dish["base"], dish["extra"], dish["from"]), (4036, 200, 3900, True))
        self.assertEqual(dish["choices"], [{"id": "b1", "values": [{"id": "v2", "count": 3, "price": 1300}]}])

    def test_amounts_wolt_states_in_whole_units_are_kept_in_hundredths(self):
        # Measured in Reykjavik: Wolt states a milk at 355 kronur as 355, where it states one at 3.55 lari as 355 too.
        with mock.patch.object(wolt, "fetch", answering({"items/search": self.REPLY})):
            offers = {offer["id"]: offer for offer in wolt.shelf({**self.STORE, "scale": 100}, "anything", *POINT)}
        self.assertEqual((offers["milk"]["price"], offers["milk"]["list"], offers["milk"]["base"]), (54900, 62500, 54900))
        self.assertEqual((offers["razor"]["price"], offers["franui"]["bulk"]), (120000, [2, 73500]))
        dish = offers["set"]
        self.assertEqual((dish["price"], dish["extra"], dish["choices"][0]["values"][0]["price"]), (403600, 390000, 1300))  # the choices go back to Wolt as it stated them


class WoltPricing(unittest.TestCase):
    STORE = {"venue_id": "v", "currency": "GEL", "country": "GEO", "scale": 1, "offer_ids": ["c1"], "every_offer_id": ["c1", "new-customers"]}

    def row(self, label, amount, original=None):
        return {"template": "amount_row", "label": label, "amount": {"amount": amount}, "original_amount": {"amount": original} if original else None}

    def test_goods_fees_and_offers_are_read_up_to_the_total(self):
        rows = [{"template": "fees_explanation_row"}, self.row("Item subtotal", 3430, 4900), self.row("Service fee", 274), self.row("Delivery (610 m)", 159),
                {"template": "price_total_amount_row", "label": "Total", "price_total_amount": {"amount": 3863}},
                self.row("Applied offers", 0), {"template": "discount_row", "label": "Buy Any 2x Franui & Get 30% OFF"}]
        sent = {}
        with mock.patch.object(wolt, "fetch", answering({"pages/checkout": lambda body: sent.update(body) or {"checkout_rows": rows}})):
            priced = wolt.quote(self.STORE, [({"id": "franui", "base": 2450, "price": 2450}, 2)], *POINT)
        self.assertEqual(priced, {"goods": 3430, "fees": [("Service fee", 274), ("Delivery (610 m)", 159)], "offers": ["Buy Any 2x Franui & Get 30% OFF"],
                                  "mine": False, "note": None})
        plan = sent["purchase_plan"]
        self.assertEqual(plan["use_promo_discount_ids"], ["c1"])
        self.assertEqual({k: plan["menu_items"][0][k] for k in ("id", "count", "base_price", "end_amount")}, {"id": "franui", "count": 2, "base_price": 2450, "end_amount": 4900})

    def test_a_store_in_whole_units_is_asked_in_them_and_answered_in_hundredths(self):
        rows = [self.row("Item subtotal", 710), self.row("Delivery (2.1 km)", 869)]
        sent = {}
        with mock.patch.object(wolt, "fetch", answering({"pages/checkout": lambda body: sent.update(body) or {"checkout_rows": rows}})):
            priced = wolt.quote({**self.STORE, "scale": 100}, [({"id": "milk", "base": 35500, "price": 35500}, 2)], *POINT)
        line = sent["purchase_plan"]["menu_items"][0]
        self.assertEqual((line["base_price"], line["end_amount"]), (355, 710))
        self.assertEqual((priced["goods"], priced["fees"]), (71000, [("Delivery (2.1 km)", 86900)]))

    def test_a_line_names_its_shelf_category_which_checkout_matches_campaigns_on(self):
        sent = {}
        with mock.patch.object(wolt, "fetch", answering({"pages/checkout": lambda body: sent.update(body) or {"checkout_rows": []}})):
            wolt.quote(self.STORE, [({"id": "wafer", "base": 199, "price": 139, "category": "sweets"}, 1), ({"id": "loose", "base": 100, "price": 100}, 1)], *POINT)
        self.assertEqual([line["category_id"] for line in sent["purchase_plan"]["menu_items"]], ["sweets", "loose"])

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
            self.campaign("Blue Friday", {"item_discount": {"fraction": 0.3, "include": {"categories": ["sweets"], "items": None}}}),
            self.campaign("3 GEL off", {"item_discount": {"amount_per_item": 300, "include": {"items": ["razor"]}}}),
            self.campaign("Combo", {"item_discount": {"fraction": 0.32, "exclude_options": True, "include": {"items": ["set"]}}}),
            self.campaign("Members' shelf", {"item_discount": {"fraction": 0.5, "include": {"items": ["milk"]}}}, {"has_wolt_plus": True}),
            self.campaign("GEL10 off on orders over GEL60", {"basket_discount": {"amount": 1000}}, {"basket_contains": [{"min_amount": 6000}]}),
            self.campaign("GEL0 delivery fee", {"delivery_discount": {"fraction": 1.0}}, points=["For new users with a local phone number."]),
        ]
        dynamic = {"venue": {"delivery_open_status": {"is_open": True}, "online": True, "open_status": {"value": "Open until 23:00"},
                             "delivery_configs": [{"schedule": "standard", "estimate": {"label": "30-40 min"}}]},
                   "venue_raw": {"discounts": campaigns, "delivery_specs": {"order_minimum_no_surcharge": 2500, "delivery_pricing": {"price_ranges": [
                       {"min": 0, "max": 1250, "a": 1350, "b": -1.0}, {"min": 1250, "max": 6238, "a": 0, "b": 0.08}, {"min": 6238, "max": 0, "a": 499, "b": 0.0}]}}}}
        static = {"venue": {"name": " Market ", "share_url": "https://wolt.com/x", "currency": "GEL", "id": "v", "country": "GEO", "rating": {"score": "9.4"}}}
        probe = {"checkout_rows": [{"template": "amount_row", "label": "Delivery (610 m)", "amount": {"amount": 259, "formatted_amount": "GEL2.59"}}],
                 "telemetry": {"delivery_price": 259, "small_order_fee": 399}, "purchase_validation": {"bag_fee": 40}}
        sent = {}
        table = {"/static": static, "/dynamic/": dynamic, "pages/checkout": lambda body: sent.update(body) or probe}
        with mock.patch.object(wolt, "fetch", answering(table)):
            record = wolt.store("market", *POINT)
        self.assertEqual((record["name"], record["open"], record["eta"], record["distance"], record["rating"]), ("Market", True, "30-40 min", "610 m", "9.4"))
        self.assertEqual((record["scale"], record["fees"][0]["segments"]), (1, [[0, None, 259, 0]]))
        self.assertEqual(record["offer_ids"], ["30% off shampoo", "2x Franui", "Blue Friday", "3 GEL off", "Combo", "GEL10 off on orders over GEL60"])
        self.assertEqual(sorted(record["every_offer_id"]), sorted(record["offer_ids"] + ["Members' shelf", "GEL0 delivery fee"]))
        self.assertEqual(sent["purchase_plan"]["use_promo_discount_ids"], record["offer_ids"])
        self.assertEqual(record["item_offers"], {"shampoo": cut(0.3), "franui": cut(0.3, units=2), "razor": cut(amount=300), "set": cut(0.32, base_only=True)})
        self.assertEqual(record["category_offers"], {"sweets": cut(0.3)})
        self.assertEqual([fee["label"] for fee in record["fees"]], ["Delivery", "Service fee", "Small order fee", "Bag", "Offer: GEL10 off on orders over GEL60"])
        self.assertEqual(record["fees"][2]["on"], "list")
        self.assertIn("offer: GEL10 off on orders over GEL60 (counted in the totals)", record["notes"])
        self.assertIn("offer: GEL0 delivery fee (new customers; not counted)", record["notes"])

    def read_store(self, campaigns, delivery):
        """A store read from Wolt, with these campaigns and this wording of its delivery price."""
        dynamic = {"venue": {"delivery_open_status": {"is_open": True}, "online": True, "open_status": {"value": "Open"}, "delivery_configs": []},
                   "venue_raw": {"discounts": campaigns, "delivery_specs": {"order_minimum_no_surcharge": 3000, "delivery_pricing": {"price_ranges": [
                       {"min": 0, "max": 0, "a": 259, "b": 0.0}]}}}}
        static = {"venue": {"name": "Market", "share_url": "https://wolt.com/x", "currency": "ISK", "id": "v", "country": "ISL"}}
        probe = {"checkout_rows": [{"template": "amount_row", "label": "Item subtotal", "amount": {"amount": 1, "formatted_amount": delivery[:3] + "0"}},
                                   {"template": "amount_row", "label": "Delivery (2.1 km)", "amount": {"amount": 869, "formatted_amount": delivery}}],
                 "telemetry": {"delivery_price": 869, "small_order_fee": 699}, "purchase_validation": {"bag_fee": 0}}
        with mock.patch.object(wolt, "fetch", answering({"/static": static, "/dynamic/": dynamic, "pages/checkout": probe})):
            return wolt.store("market", *POINT)

    def test_a_currency_stated_in_whole_units_is_recognised_from_wolt_s_own_wording(self):
        # Measured in Reykjavik and Budapest: 869 beside "ISK869" is 869 kronur, and 223,700 beside "HUF2,237" is 2,237 forints.
        kronur = self.read_store([], "ISK869")
        self.assertEqual(kronur["scale"], 100)
        self.assertEqual(kronur["fees"][0], {"label": "Delivery", "segments": [[0, None, 86900, 0]]})
        self.assertEqual(kronur["fees"][2]["segments"], [[0, 230100, 69900, 0], [230100, 300000, 300000, -1]])
        self.assertEqual(self.read_store([], "HUF8.69")["scale"], 1)

    def test_an_offer_published_as_one_smallest_unit_is_listed_and_not_counted(self):
        # Measured in Tel Aviv: "25 off with code" is published as a discount of one agora, which checkout would take off.
        coded = self.campaign("₪25 off with code BF25W", {"basket_discount": {"amount": 1}})
        record = self.read_store([coded], "ISK869")
        self.assertEqual((record["offer_ids"], record["every_offer_id"]), ([], []))
        self.assertEqual(record["notes"], ["offer: ₪25 off with code BF25W (needs a code or pays in points; not counted)"])
        self.assertEqual([fee["label"] for fee in record["fees"]], ["Delivery", "Service fee", "Small order fee"])

    def test_free_delivery_within_a_distance_counts_for_a_store_that_near(self):
        # Measured at Farmers Market Vera: delivery 3.09 under 20.00 of goods and nothing from 20.00, for a store within 5 km.
        offer = self.campaign("GEL0 delivery fee on orders over GEL20", {"delivery_discount": {"fraction": 1.0}},
                              {"basket_contains": [{"min_amount": 2000}], "delivery_methods": ["homedelivery"], "max_distance": 5000})
        self.assertEqual(wolt.offer_segments(offer, 309, 1200.0), [[2000, None, -309, 0]])
        self.assertIsNone(wolt.offer_segments(offer, 309, 6100.0))
        self.assertIsNone(wolt.offer_segments(offer, 309, None))

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
            "3": self.dish(3, "Shawarma", 15.0, 60, option_group_presence="only_optional", order_limit_quantity=4),
            "4": {"type": "category", "id": 4},
            "5": self.dish(5, "Out", 1.0, 99, availability="out_of_stock"),
            "6": self.dish(6, "DAIRYLAND Danablue 2*3.2 kg", 6.5, 40, selling_unit="kg"),
        }
        with mock.patch.object(bolt, "fetch", answering({"searchInMenu": {"code": 0, "data": {"items": items}}})):
            offers = bolt.shelf({"key": "99610"}, "x", *POINT)
        self.assertEqual([offer["name"] for offer in offers],
                         ["Butter Valio 500 gr", "Shawarma", "Cheese / Frico / Gouda briquette 100 g", "DAIRYLAND Danablue 2*3.2 kg"])
        # A product reckoned by weight with no price per kilogram has no size to trust: its name gives the wheel it is cut from.
        self.assertEqual([(offer["price"], offer["size"], offer["from"], offer["limit"]) for offer in offers],
                         [(3695, [500, "g"], False, None), (1500, None, True, 4), (450, [100, "g"], False, None), (650, None, False, None)])

    def test_a_dish_starts_at_its_cheapest_obligatory_choices(self):
        # Measured at provider 12088: "Pizza 33Cm" is listed at 0.10 and cannot be ordered without two halves, the cheapest at 10.95 and 13.95.
        def option(ident, price, availability="in_stock"):
            return {"type": "option_multi_select", "id": ident, "price": {"value": price}, "availability": availability}
        items = {
            "1": self.dish(1, "Pizza 33Cm", 0.1, 50, option_group_presence="required_or_preselected", child_ids=[10, 20]),
            "10": {"type": "option_multi_select_group", "id": 10, "min": 2, "max": 2, "is_required": True, "child_ids": [11, 12, 13, 14]},
            "11": option(11, 17.95), "12": option(12, 13.95), "13": option(13, 10.95), "14": option(14, 5.0, "out_of_stock"),
            "20": {"type": "option_multi_select_group", "id": 20, "min": 0, "max": 1, "is_required": False, "child_ids": [21]},
            "21": option(21, 3.5),
        }
        with mock.patch.object(bolt, "fetch", answering({"searchInMenu": {"code": 0, "data": {"items": items}}})):
            pizza, = bolt.shelf({"key": "12088"}, "x", *POINT)
        self.assertEqual((pizza["price"], pizza["from"]), (2500, True))

    def test_a_refused_call_is_an_error_naming_it(self):
        with mock.patch.object(bolt, "fetch", answering({"searchInMenu": {"code": 702, "message": "INVALID_REQUEST"}})):
            with self.assertRaisesRegex(RuntimeError, "Bolt searchInMenu: INVALID_REQUEST"):
                bolt.shelf({"key": "1"}, "x", *POINT)

    def test_a_point_bolt_does_not_serve_is_said_in_plain_words(self):
        with mock.patch.object(bolt, "fetch", answering({"deliverySearch": {"code": 4500, "message": "CITY_NOT_FOUND"}})):
            with self.assertRaisesRegex(RuntimeError, "^Bolt Food does not deliver to this point$"):
                bolt.discover("milk", 64.1466, -21.9426, False)

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
    PLACE = {"cityCode": "TBI", "countryCode": "GE", "addressComponents": {"administrative_area_level_1": "Tbilisi", "locality": "T'bilisi"}}

    def card(self, slug, category, is_open="true"):
        return {"type": "STORE_CARD_V2", "data": {"slug": slug, "title": {"text": {"text": slug.upper()}}},
                "actions": [{"data": {"events": [{"data": {"shopIsOpen": is_open, "glovoCategoryId": category}}]}}]}

    def row(self, *prices):
        return {"type": "CAROUSEL", "data": {"elements": [{"data": {"pricing": {"finalPrice": price}}} for price in prices]}}

    def search(self, food):
        elements = [{"type": "DISCLAIMERS", "data": {}}, self.card("spar", "4"), self.row("4,49 ₾", "5,60 ₾"), self.card("cafe", "1"), self.row("14,00 ₾"),
                    self.card("night", "4", "false"), self.row("3,00 ₾"), self.card("nameonly", "4")]
        table = {"addresslookup": self.PLACE, "seo-content": {}, "store_wall/search": {"data": {"body": {"data": {"elements": elements}}}}}
        with mock.patch.object(glovo, "fetch", answering(table)), mock.patch.dict(glovo._places, clear=True):
            return glovo.discover("milk", *POINT, food)

    def test_the_search_screen_is_read_card_by_card(self):
        self.assertEqual(self.search(False), [
            {"store": "spar", "name": "SPAR", "open": True, "price": 449}, {"store": "spar", "name": "SPAR", "open": True, "price": 560},
            {"store": "night", "name": "NIGHT", "open": False, "price": 300}])
        self.assertEqual(self.search(True), [{"store": "cafe", "name": "CAFE", "open": True, "price": 1400}])

    def test_groceries_are_searched_on_their_own_when_the_search_shows_products_for_few_stores(self):
        # Measured in Barcelona: "huevos" across every kind showed products for restaurants only, and for 22 grocery stores once groceries were asked for.
        asked = []

        def screen(url):
            asked.append(url.split("search?")[1])
            store = "mercadona" if "categoryId=4" in url else "farmacia"
            return {"data": {"body": {"data": {"elements": [{"data": {"title": "an element of no type"}}, self.card(store, "4" if store == "mercadona" else "3"), self.row("2,10 €")]}}}}
        with mock.patch.object(glovo, "fetch", lambda url, headers=None, body=None, **more: self.PLACE if "addresslookup" in url else {} if "seo-content" in url else screen(url)), \
                mock.patch.dict(glovo._places, clear=True):
            stores = [hit["store"] for hit in glovo.discover("huevos", *POINT, False)]
            dishes = glovo.discover("huevos", *POINT, True)
        self.assertEqual(stores, ["farmacia", "mercadona"])
        self.assertEqual(asked, ["searchQuery=huevos", "searchQuery=huevos&categoryId=4", "searchQuery=huevos&categoryId=1"])
        self.assertEqual(dishes, [])

    def test_a_search_that_shows_products_for_enough_stores_is_not_repeated_among_the_groceries(self):
        asked = []

        def screen(url):
            asked.append(url.split("search?")[1])
            return {"data": {"body": {"data": {"elements": [part for store in ("spar", "fresco", "nikora") for part in (self.card(store, "4"), self.row("4,49 ₾"))]}}}}
        with mock.patch.object(glovo, "fetch", lambda url, headers=None, body=None, **more: self.PLACE if "addresslookup" in url else {} if "seo-content" in url else screen(url)), \
                mock.patch.dict(glovo._places, clear=True):
            self.assertEqual([hit["store"] for hit in glovo.discover("milk", *POINT, False)], ["spar", "fresco", "nikora"])
        self.assertEqual(asked, ["searchQuery=milk"])

    def test_a_country_glovo_is_not_in_is_said_at_once(self):
        # Measured for Helsinki: Glovo names a city all the same, has no page for the country, and no server answers a search there.
        calls = []

        def fetch(url, headers=None, body=None, patient=True, **more):
            calls.append((url.split("glovoapp.com")[1].split("?")[0], patient))
            if "addresslookup" in url:
                return {"cityCode": "SUW", "countryCode": "FI", "addressComponents": {"country": "Finland", "locality": "Helsinki"}}
            failure = RuntimeError("answered")
            failure.status = 404 if "seo-content" in url else 503
            raise failure
        with mock.patch.object(glovo, "fetch", fetch), mock.patch.dict(glovo._places, clear=True):
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, "^Glovo does not operate in Finland$"):
                    glovo.discover("maito", 60.1699, 24.9384, False)
        self.assertEqual(calls, [("/v3/addresslookup/pub/coordinates", True), ("/seo-content/locales/en/countries/fi", True), ("/v1/web/store_wall/search", False)])

    def test_a_card_without_the_store_s_state_stops_the_search_with_its_name(self):
        elements = [{"type": "STORE_CARD_V2", "data": {"slug": "odd"}}]
        table = {"addresslookup": self.PLACE, "seo-content": {}, "store_wall/search": {"data": {"body": {"data": {"elements": elements}}}}}
        with mock.patch.object(glovo, "fetch", answering(table)), mock.patch.dict(glovo._places, clear=True):
            with self.assertRaisesRegex(RuntimeError, "odd"):
                glovo.discover("milk", *POINT, False)

    def test_a_shelf_carries_promotions_sizes_and_choices(self):
        products = [
            {"id": 1, "name": "რძე /სოფლის ნობათი/ 2,5% 950მლ", "price": 6.2, "promotion": {"price": 5.49, "title": "-0,71 ₾", "isPrime": False}},
            {"id": 2, "name": "პიცა", "price": 30.0, "promotion": {"price": 18.0, "title": "-40%", "isPrime": True}, "attributeGroups": [{"id": 1}]},
            {"id": 3, "name": "კვერცხი 10ც", "price": 5.8, "description": " fresh "},
            # Measured at Wendy's: a combo listed at 13.90 whose size must be chosen, the choices adding 1.95 or 3.90.
            {"id": 4, "name": "ვეჯი ბურგერის კომბო", "price": 13.9, "attributeGroups": [
                {"id": 7, "min": 1, "max": 1, "attributes": [{"priceImpact": 3.9}, {"priceImpact": 1.95}]},
                {"id": 8, "min": 0, "max": 3, "attributes": [{"priceImpact": 0.5}]}]},
        ]
        table = {"addresslookup": self.PLACE, "seo-content": {}, "/search?query=": {"results": [{"products": products}]}}
        with mock.patch.object(glovo, "fetch", answering(table)), mock.patch.dict(glovo._places, clear=True):
            milk, pizza, eggs, combo = glovo.shelf({"store_id": 1, "address_id": 2}, "x", *POINT)
        self.assertEqual((milk["price"], milk["list"], milk["size"]), (549, 620, [950, "ml"]))
        self.assertEqual((pizza["price"], pizza["from"], pizza["note"]), (3000, True, "offer: -40% (Prime members)"))
        self.assertEqual((eggs["size"], eggs["note"]), ([10, "pc"], "fresh"))
        self.assertEqual((combo["price"], combo["list"], combo["from"]), (1585, 1585, True))

    def test_a_store_counts_a_whole_menu_offer_and_lists_the_rest(self):
        info = {"id": 26609, "addressId": 687129, "name": "Gennaro", "slug": "gennaro-tbi", "open": True, "rating": "97%", "distance": "4km",
                "deliveryFeeInfo": {"fee": 5.99}, "serviceFeeInfo": {"minValue": 129, "maxValue": 499, "setupValue": 9}, "primeAvailable": True,
                "promotions": [{"title": "Free delivery on the first order", "type": "FREE_DELIVERY", "description": ""},
                               {"title": "-20%", "type": "BASKET_PERCENTAGE", "description": "whole menu", "minimumBasketSizeCents": 4000, "percentage": 20.0},
                               {"title": "-25%", "type": "BASKET_PERCENTAGE", "description": "whole menu", "minimumBasketSizeCents": 4000, "percentage": 25.0, "prime": True}]}
        ranges = [{"lowerBound": 0.0, "upperBound": 15.0, "upperBoundInfo": {"currencyCode": "GEL"}, "surchargeInfo": {"amount": 1.99}, "surchargeStrategy": "CAPPED"}]
        table = {"addresslookup": self.PLACE, "seo-content": {}, "/v3/stores/gennaro-tbi": info, "node/store_fees": {"data": {"ranges": ranges}}}
        with mock.patch.object(glovo, "fetch", answering(table)), mock.patch.dict(glovo._places, clear=True):
            record = glovo.store("gennaro-tbi", *POINT)
        self.assertEqual(record["url"], "https://glovoapp.com/en/ge/tbilisi/stores/gennaro-tbi")
        self.assertEqual([fee["label"] for fee in record["fees"]], ["Delivery", "Service fee", "Small order fee", "Offer: -20% whole menu, baskets from 40.00"])
        self.assertEqual(record["fees"][3]["segments"], [[4000, None, 0, -0.2]])
        self.assertEqual(record["notes"][:3], ["offer: Free delivery on the first order", "offer: -20% whole menu, baskets from 40.00 (counted in the totals)",
                                               "offer: -25% whole menu, baskets from 40.00 (Prime members)"])
        self.assertEqual((record["currency"], record["distance"], record["open"]), ("GEL", "4km", True))

    def test_a_store_s_address_names_the_city_as_glovo_s_pages_spell_it(self):
        # Barcelona lies in the region Catalunya; Glovo's full page for a store there is the one under "barcelona".
        info = {"id": 1, "addressId": 2, "name": "Paul", "slug": "paul-barcelona", "open": True, "deliveryFeeInfo": {"fee": 0.99}}
        place = {"cityCode": "BCN", "countryCode": "ES", "addressComponents": {"administrative_area_level_1": "Catalunya", "locality": "Barcelona"}}
        for components, city in ((place["addressComponents"], "barcelona"), ({"locality": "Sant Cugat del Vallès"}, "sant-cugat-del-valles"), ({}, "bcn")):
            table = {"addresslookup": {**place, "addressComponents": components}, "seo-content": {}, "/v3/stores/paul-barcelona": info, "node/store_fees": {"data": {"ranges": []}}}
            with self.subTest(city=city), mock.patch.object(glovo, "fetch", answering(table)), mock.patch.dict(glovo._places, clear=True):
                self.assertEqual(glovo.store("paul-barcelona", 41.3874, 2.1686)["url"], f"https://glovoapp.com/en/es/{city}/stores/paul-barcelona")


if __name__ == "__main__":
    unittest.main()
