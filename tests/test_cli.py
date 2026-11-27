import contextlib
import io
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

loader = SourceFileLoader("shopmaster_cli", str(ROOT / "bin" / "shopmaster"))
cli = module_from_spec(spec_from_loader(loader.name, loader))
loader.exec_module(cli)


def offer(name, price, **extra):
    return {"id": name, "name": name, "price": price, "list": price, **extra}


def store(platform, name, offers, delivery=250, minimum=2500, **extra):
    return {
        "platform": platform, "key": name.lower(), "name": name, "url": f"https://example.test/{name.lower()}",
        "currency": "GEL", "open": True, "opens": "Opens at 09:00", "eta": "30-40 min", "distance": "1 km", "rating": "9.1",
        "caveat": None, "notes": [],
        "fees": [
            {"label": "Delivery", "segments": [[0, None, delivery, 0]]},
            {"label": "Small order", "segments": [[0, minimum, minimum, -1]]},
        ],
        "offers": offers, "failed": {}, **extra,
    }


def sample_run():
    return {
        "shape": cli.RUN_SHAPE, "at": "2026-11-27T03:00+04:00", "food": False, "point": {"lat": 41.69, "lon": 44.8, "label": "home"},
        "picks": {}, "unread": {}, "issued": {"alpha": 1, "beta": 1},
        "wants": {"milk": {"count": 1, "queries": ["milk"]}, "eggs": {"count": 1, "queries": ["eggs"]}, "rice": {"count": 2, "queries": ["rice"]}},
        "stores": {
            "a1": store("alpha", "Alpha", {"milk": [offer("Chocolate milk 200ml", 300), offer("Milk 1L", 550)], "eggs": [offer("Eggs 10", 600)], "rice": []}),
            "b1": store("beta", "Beta", {"milk": [offer("Milk 1L", 560)], "eggs": [offer("Eggs 10", 590)], "rice": [offer("Rice 1kg", 800)]}),
        },
    }


def quiet(function, **options):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        function(SimpleNamespace(**options))
    return out.getvalue()


class ParseWant(unittest.TestCase):
    def test_packs_amounts_and_queries(self):
        self.assertEqual(cli.parse_want("eggs*2=eggs|კვერცხი"), ("eggs", {"count": 2, "queries": ["eggs", "კვერცხი"]}))
        self.assertEqual(cli.parse_want("milk"), ("milk", {"count": 1, "queries": ["milk"]}))
        self.assertEqual(cli.parse_want("eggs*20pc=eggs"), ("eggs", {"amount": [20, "pc"], "queries": ["eggs"]}))
        self.assertEqual(cli.parse_want("milk*2l=milk 1l"), ("milk", {"amount": [2000, "ml"], "queries": ["milk 1l"]}))
        self.assertEqual(cli.parse_want("rice*1.5kg=rice"), ("rice", {"amount": [1500, "g"], "queries": ["rice"]}))

    def test_what_cannot_be_bought_is_refused_with_a_message(self):
        for spec in ("eggs*two=eggs", "eggs*0=eggs", "eggs*-1=eggs", "milk*0.5=milk", "two words=milk", "a.b=milk"):
            with self.subTest(spec=spec), self.assertRaises(SystemExit) as refusal:
                cli.parse_want(spec)
            self.assertIn(spec, str(refusal.exception))


class Cli(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        cli.RUN_FILE = Path(folder.name) / "run.json"
        cli.PLATFORMS = {"alpha": SimpleNamespace(), "beta": SimpleNamespace()}  # platforms that price nothing themselves
        cli.save(cli.RUN_FILE, sample_run())

    def solve(self, **options):
        return quiet(cli.solve, **{"max_stores": 2, "top": 3, "closed": False, **options})

    def change(self, mutate):
        run = sample_run()
        mutate(run)
        cli.save(cli.RUN_FILE, run)

    def test_first_candidate_stands_until_a_pick_replaces_it(self):
        self.assertIn("milk: 1 × Chocolate milk 200ml", self.solve())
        quiet(cli.pick, picks=["a1.milk=2"])
        self.assertNotIn("Chocolate", self.solve())

    def test_the_number_of_packs_multiplies_the_price_and_a_pick_can_override_it(self):
        self.assertIn("rice: 2 × Rice 1kg  16.00", self.solve())
        quiet(cli.pick, picks=["b1.rice=1x3"])
        self.assertIn("rice: 3 × Rice 1kg  24.00", self.solve())

    def test_an_amount_is_turned_into_packs_from_each_candidate_s_size(self):
        def ask_for_twenty(run):
            run["wants"]["eggs"] = {"amount": [20, "pc"], "queries": ["eggs"]}
            run["stores"]["a1"]["offers"]["eggs"] = [offer("Eggs", 700), offer("Eggs 10", 600, size=[10, "pc"]), offer("Eggs 15", 850, size=[15, "pc"])]
            run["stores"]["b1"]["offers"]["eggs"] = [offer("Egg, farm", 125)]
        self.change(ask_for_twenty)
        table = quiet(cli.show, ref=None)
        self.assertIn(" 1  Eggs  7.00  → size unknown", table)
        self.assertIn("*2  Eggs 10  [10 pc]  6.00 (0.60/pc)  → ×2", table)
        self.assertIn(" 3  Eggs 15  [15 pc]  8.50 (0.57/pc)  → ×2", table)
        self.assertIn("(none stands: no pack size here compares with the amount asked; pick one with its number, as in b1.eggs=1x2)", table)
        self.assertIn("eggs: 2 × Eggs 10 [10 pc]  12.00", self.solve(max_stores=1))
        self.assertNotIn("Egg, farm", self.solve())

    def test_a_pack_of_unknown_size_stands_only_with_a_number_to_buy(self):
        def ask_for_twenty(run):
            run["wants"]["eggs"] = {"amount": [20, "pc"], "queries": ["eggs"]}
            run["stores"]["b1"]["offers"]["eggs"] = [offer("Egg, farm", 125)]
        self.change(ask_for_twenty)
        with self.assertRaises(SystemExit) as refusal:
            quiet(cli.pick, picks=["b1.eggs=1"])
        self.assertIn("b1.eggs=1x2", str(refusal.exception))
        quiet(cli.pick, picks=["b1.eggs=1x20"])
        self.assertIn("eggs: 20 × Egg, farm  25.00", self.solve())

    def test_a_discount_for_several_units_applies_from_that_many(self):
        self.change(lambda run: run["stores"]["b1"]["offers"].update(rice=[offer("Rice 1kg", 800, bulk=[2, 200])]))
        self.assertIn("rice: 2 × Rice 1kg  12.00", self.solve())
        quiet(cli.pick, picks=["b1.rice=1x1"])
        self.assertIn("rice: 1 × Rice 1kg  8.00", self.solve())

    def test_a_campaign_s_discount_is_rounded_on_each_unit_as_checkout_rounds_it(self):
        # Measured on Wolt: 30% off from two units, three units of 9.95, charged 20.88 (6.96 each) where 30% of the line would give 20.89.
        self.change(lambda run: run["stores"]["b1"]["offers"].update(rice=[offer("Rice 1kg", 995, bulk=[2, 299])]))
        quiet(cli.pick, picks=["b1.rice=1x3"])
        self.assertIn("rice: 3 × Rice 1kg  20.88", self.solve())

    def test_more_than_one_order_may_take_is_said(self):
        self.change(lambda run: run["stores"]["b1"]["offers"].update(rice=[offer("Rice 1kg", 800, limit=3, stock=40)]))
        quiet(cli.pick, picks=["b1.rice=1x8"])
        self.assertIn("! rice: 8 wanted, and the store shows 3 as the most one order can take", self.solve())
        quiet(cli.pick, picks=["b1.rice=1x3"])
        self.assertNotIn("the most one order can take", self.solve())

    def test_a_run_kept_by_another_version_is_gathered_afresh(self):
        self.change(lambda run: run.update(shape=1))
        with self.assertRaises(SystemExit) as refusal:
            self.solve()
        self.assertIn("Gather afresh", str(refusal.exception))

    def test_dropping_the_only_candidate_makes_the_item_missing_there(self):
        quiet(cli.pick, picks=["b1.rice=-"])
        report = self.solve()
        self.assertIn("WITHOUT rice", report)
        self.assertIn("rice: no open store in the run offers it", report)

    def test_pick_refuses_what_it_cannot_use(self):
        for bad in ("a1.milk=7", "a1.milk=1xabc", "a1.milk=1x0", "a1.rice=1", "z9.milk=1"):
            with self.subTest(pick=bad), self.assertRaises(SystemExit):
                quiet(cli.pick, picks=[bad])

    def test_dropped_store_leaves_the_run_with_its_picks(self):
        quiet(cli.pick, picks=["a1.milk=2"])
        quiet(cli.drop, refs=["a1"])
        run = cli.load(cli.RUN_FILE, "run")
        self.assertEqual(list(run["stores"]), ["b1"])
        self.assertEqual(run["picks"], {})

    def test_closed_store_is_left_out_and_said_so(self):
        self.change(lambda run: run["stores"]["b1"].update(open=False))
        report = self.solve()
        self.assertIn("left out: b1 Beta is closed", report)
        self.assertNotIn("b1  Beta", report)
        self.assertIn("b1  Beta · Beta · CLOSED (Opens at 09:00)", self.solve(closed=True))

    def test_failed_lookup_is_reported_as_unknown_not_as_absent(self):
        self.change(lambda run: run["stores"]["a1"]["failed"].update(rice="api.example.test/search answered 429"))
        self.assertIn("a1 rice: a lookup failed, so the candidates may be incomplete (api.example.test/search answered 429)", self.solve())
        self.assertIn("?  lookup failed, so unknown", quiet(cli.show, ref="a1"))

    def test_a_store_that_could_not_be_read_is_reported_with_every_report(self):
        self.change(lambda run: run["unread"].update({"alpha:gamma": "api.example.test/store could not be reached (no route)"}))
        for report in (self.solve(), quiet(cli.show, ref=None)):
            self.assertIn("! alpha:gamma: the store could not be read (api.example.test/store could not be reached (no route))", report)

    def test_threshold_hint_is_printed_when_the_extra_goods_mostly_pay_for_themselves(self):
        self.change(lambda run: run["stores"]["b1"]["offers"].update(rice=[offer("Rice 1kg", 500)]))
        self.assertIn("3.50 more goods here would cut the fees by 3.50", self.solve(max_stores=1, top=1))

    def test_show_marks_the_standing_candidate(self):
        table = quiet(cli.show, ref=None)
        self.assertIn("*1  Chocolate milk 200ml", table)
        self.assertIn(" 2  Milk 1L", table)
        self.assertIn("-  nothing found", table)
        self.assertIn("List: milk, eggs, rice ×2", table)

    def test_platform_pricing_replaces_the_planning_fees(self):
        priced = {"goods": 2750, "fees": [("Delivery (1 km)", 199), ("Bag", 20)], "offers": []}
        cli.PLATFORMS["beta"] = SimpleNamespace(quote=lambda store, lines, lat, lon: priced)
        report = self.solve(max_stores=1, top=1)
        self.assertIn("goods 27.50 + Delivery (1 km) 1.99 + Bag 0.20 = 29.69  (priced by Beta)", report)
        self.assertIn("1. 29.69 in 1 order", report)

    def test_offers_the_platform_applies_to_the_goods_show_as_a_line(self):
        priced = {"goods": 2350, "fees": [("Delivery (1 km)", 199)], "offers": ["Buy 2 get 25% off"]}
        cli.PLATFORMS["beta"] = SimpleNamespace(quote=lambda store, lines, lat, lon: priced)
        self.assertIn("goods 27.50 − Offers: Buy 2 get 25% off 4.00 + Delivery (1 km) 1.99 = 25.49  (priced by Beta)", self.solve(max_stores=1, top=1))

    def test_failed_platform_pricing_keeps_the_planning_fees_and_says_so(self):
        def refuse(store, lines, lat, lon):
            raise RuntimeError("api.example.test/checkout answered 503")
        cli.PLATFORMS["beta"] = SimpleNamespace(quote=refuse)
        report = self.solve(max_stores=1, top=1)
        self.assertIn("! Beta did not price this basket (api.example.test/checkout answered 503)", report)
        self.assertIn("1. about 30.00 in 1 order", report)

    def test_estimated_and_partial_fees_mark_the_total(self):
        self.change(lambda run: run["stores"]["b1"].update(caveat="built from published parameters"))
        self.assertIn("1. about 30.00 in 1 order", self.solve(max_stores=1, top=1))
        self.change(lambda run: run["stores"]["b1"].update(caveat="delivery price only", partial=True))
        report = self.solve(max_stores=1, top=1)
        self.assertIn("at least 30.00 in 1 order", report)
        self.assertIn("(delivery price only)", report)

    def test_the_best_plan_with_every_fee_known_is_shown_beside_cheaper_looking_ones(self):
        def hide_fees(run):
            run["stores"]["b1"].update(caveat="delivery price only", partial=True)
            run["stores"]["b1"]["fees"] = run["stores"]["b1"]["fees"][:1]
            run["stores"]["a1"]["offers"]["rice"] = [offer("Rice 1kg", 1000)]
        self.change(hide_fees)
        report = self.solve(top=1)
        self.assertIn("1. at least 30.00 in 1 order, everything covered  [best single order]", report)
        self.assertIn("2. about 31.50 in 1 order, everything covered  [best with every fee known]", report)


def shop(shelves, broken=(), closed=()):
    """A platform with fixed shelves: {store: {query: [(name, price), ...]}}. A store named in `broken` fails its first read."""
    broken = set(broken)

    def discover(query, lat, lon, food):
        return [{"store": key, "name": key.title(), "open": None, "price": price}
                for key, shelf in shelves.items() for _, price in shelf.get(query, [])]

    def read(key, lat, lon):
        if key in broken:
            broken.remove(key)
            raise RuntimeError("shop.example.test/store could not be reached (no route)")
        record = store("shop", key.title(), {}, open=key not in closed)
        return {field: value for field, value in record.items() if field not in ("platform", "key", "offers", "failed")}

    def shelf(record, query, lat, lon):
        if query == "broken-query":
            raise RuntimeError("shop.example.test/search answered 429")
        return [offer(name, price) for name, price in shelves[record["key"]].get(query, [])]

    return SimpleNamespace(discover=discover, store=read, shelf=shelf)


class Gather(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        cli.RUN_FILE = Path(folder.name) / "run.json"
        cli.POINT_FILE = Path(folder.name) / "point.json"
        cli.save(cli.POINT_FILE, {"lat": 41.69, "lon": 44.8, "label": "home"})
        self.shelves = {
            "full": {"milk": [("Milk 1L", 550)], "eggs": [("Eggs 10", 600)], "kvertskhi": [("Eggs 15", 850)]},
            "half": {"milk": [("Milk 1L", 500)]},
            "pharmacy": {"paracetamol": [("Paracetamol", 420)]},
        }
        cli.PLATFORMS = {"shop": shop(self.shelves)}

    def gather(self, *wants, **options):
        defaults = {"want": list(wants), "food": False, "store": [], "per_platform": 1, "platform": None, "closed": False, "add": False}
        report = quiet(cli.gather, **{**defaults, **options})
        return report, cli.load(cli.RUN_FILE, "run")

    def stores(self, run):
        return {ref: record["key"] for ref, record in run["stores"].items()}

    def test_the_store_matching_most_of_the_list_is_read_and_the_next_is_named(self):
        report, run = self.gather("milk", "eggs")
        self.assertEqual(self.stores(run), {"s1": "full"})
        self.assertEqual([o["name"] for o in run["stores"]["s1"]["offers"]["eggs"]], ["Eggs 10"])
        self.assertIn("shop also matched: shop:half Half (1/2)", report)

    def test_an_item_the_chosen_stores_lack_brings_in_a_store_that_has_it(self):
        _, run = self.gather("milk", "eggs", "paracetamol")
        self.assertEqual(self.stores(run), {"s1": "full", "s2": "pharmacy"})

    def test_a_closed_store_is_passed_over_for_the_next_in_the_ranking(self):
        cli.PLATFORMS = {"shop": shop(self.shelves, closed=["full"])}
        report, run = self.gather("milk", "eggs")
        self.assertEqual(self.stores(run), {"s1": "half"})
        self.assertIn("! shop: Full is closed (Opens at 09:00) and was passed over", report)
        _, run = self.gather("milk", "eggs", closed=True)
        self.assertEqual(self.stores(run), {"s1": "full"})

    def test_a_store_whose_read_failed_is_replaced_now_and_read_on_the_next_add(self):
        cli.PLATFORMS = {"shop": shop(self.shelves, broken=["full"])}
        report, run = self.gather("milk", "eggs")
        self.assertEqual(self.stores(run), {"s1": "half"})
        self.assertIn("! shop:full: the store could not be read (shop.example.test/store could not be reached (no route))", report)
        report, run = self.gather(add=True)
        self.assertEqual(self.stores(run), {"s1": "half", "s2": "full"})
        self.assertEqual(run["unread"], {})
        self.assertNotIn("could not be read", report)

    def test_a_store_number_is_never_issued_twice(self):
        self.gather("milk", "eggs", per_platform=2)
        quiet(cli.drop, refs=["s2"])
        _, run = self.gather(add=True, store=["shop:pharmacy"])
        self.assertEqual(self.stores(run), {"s1": "full", "s3": "pharmacy"})

    def test_searching_an_item_afresh_replaces_its_candidates_and_forgets_its_pick(self):
        self.gather("milk", "eggs")
        quiet(cli.pick, picks=["s1.eggs=1x2", "s1.milk=1"])
        _, run = self.gather("eggs=kvertskhi", add=True)
        self.assertEqual([o["name"] for o in run["stores"]["s1"]["offers"]["eggs"]], ["Eggs 15"])
        self.assertEqual(run["picks"], {"s1.milk": {"n": 1}})

    def test_an_item_added_later_is_searched_across_stores_too(self):
        self.gather("milk", "eggs")
        _, run = self.gather("paracetamol", add=True)
        self.assertEqual(self.stores(run), {"s1": "full", "s2": "pharmacy"})

    def test_one_failed_query_among_several_is_kept_as_a_gap(self):
        report, run = self.gather("eggs=eggs|broken-query")
        self.assertEqual([o["name"] for o in run["stores"]["s1"]["offers"]["eggs"]], ["Eggs 10"])
        self.assertIn("! s1 eggs: a lookup failed, so the candidates may be incomplete (shop.example.test/search answered 429)", report)

    def test_adding_keeps_the_time_of_the_first_reading_and_notes_the_later_one(self):
        _, first = self.gather("milk")
        report, run = self.gather("eggs", add=True)
        self.assertEqual(run["at"], first["at"])
        self.assertIn("extended", report.splitlines()[0])

    def test_a_run_is_not_extended_after_the_delivery_point_has_moved(self):
        self.gather("milk")
        cli.save(cli.POINT_FILE, {"lat": 41.72, "lon": 44.78, "label": "office"})
        with self.assertRaises(SystemExit) as refusal:
            self.gather("eggs", add=True)
        self.assertIn("Gather afresh", str(refusal.exception))

    def test_a_misnamed_store_or_platform_is_refused_with_a_message(self):
        for named in (["shop-full"], ["Shop:full"]):
            with self.subTest(store=named), self.assertRaises(SystemExit) as refusal:
                self.gather("milk", store=named)
            self.assertIn("platform:key", str(refusal.exception))


if __name__ == "__main__":
    unittest.main()
