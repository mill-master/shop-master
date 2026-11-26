import contextlib
import io
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "shop-master" / "scripts"
sys.path.insert(0, str(SCRIPTS))

loader = SourceFileLoader("shopmaster_cli", str(SCRIPTS / "shopmaster"))
cli = module_from_spec(spec_from_loader(loader.name, loader))
loader.exec_module(cli)


def offer(name, price, **extra):
    return {"id": name, "name": name, "price": price, **extra}


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
        "at": "2026-11-27T03:00+04:00", "food": False, "point": {"lat": 41.69, "lon": 44.8, "label": "home"}, "picks": {},
        "wants": {"milk": {"qty": 1, "queries": ["milk"]}, "eggs": {"qty": 1, "queries": ["eggs"]}, "rice": {"qty": 2, "queries": ["rice"]}},
        "stores": {
            "a1": store("alpha", "Alpha", {"milk": [offer("Chocolate milk 200ml", 300), offer("Milk 1L", 550)], "eggs": [offer("Eggs 10", 600)], "rice": []}),
            "b1": store("beta", "Beta", {"milk": [offer("Milk 1L", 560)], "eggs": [offer("Eggs 10", 590)], "rice": [offer("Rice 1kg", 800)]}),
        },
    }


class Cli(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        cli.RUN_FILE = Path(folder.name) / "run.json"
        cli.PLATFORMS = {"alpha": SimpleNamespace(), "beta": SimpleNamespace()}  # platforms that price nothing themselves
        cli.save(cli.RUN_FILE, sample_run())

    def run_command(self, function, **options):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            function(SimpleNamespace(**options))
        return out.getvalue()

    def solve(self, **options):
        return self.run_command(cli.solve, **{"max_stores": 2, "top": 3, "closed": False, **options})

    def change(self, mutate):
        run = sample_run()
        mutate(run)
        cli.save(cli.RUN_FILE, run)

    def test_parse_want(self):
        self.assertEqual(cli.parse_want("eggs*2=eggs|კვერცხი"), ("eggs", 2.0, ["eggs", "კვერცხი"]))
        self.assertEqual(cli.parse_want("milk"), ("milk", 1, ["milk"]))

    def test_first_candidate_stands_until_a_pick_replaces_it(self):
        self.assertIn("milk: 1 × Chocolate milk 200ml", self.solve())
        self.run_command(cli.pick, picks=["a1.milk=2"])
        self.assertNotIn("Chocolate", self.solve())

    def test_want_quantity_multiplies_the_price_and_a_pick_can_override_it(self):
        self.assertIn("rice: 2 × Rice 1kg  16.00", self.solve())
        self.run_command(cli.pick, picks=["b1.rice=1x3"])
        self.assertIn("rice: 3 × Rice 1kg  24.00", self.solve())

    def test_dropping_the_only_candidate_makes_the_want_missing_there(self):
        self.run_command(cli.pick, picks=["b1.rice=-"])
        report = self.solve()
        self.assertIn("WITHOUT rice", report)
        self.assertIn("rice: no open store in the run offers it", report)

    def test_pick_rejects_a_candidate_number_that_does_not_exist(self):
        with self.assertRaises(SystemExit):
            self.run_command(cli.pick, picks=["a1.milk=7"])

    def test_dropped_store_leaves_the_run_with_its_picks(self):
        self.run_command(cli.pick, picks=["a1.milk=2"])
        self.run_command(cli.drop, refs=["a1"])
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
        def fail(run):
            del run["stores"]["a1"]["offers"]["rice"]
            run["stores"]["a1"]["failed"]["rice"] = "HTTPError: 429"
        self.change(fail)
        self.assertIn("a1 rice: lookup failed, so unknown", self.solve())
        self.assertIn("?  lookup failed, so unknown", self.run_command(cli.show, ref="a1"))

    def test_threshold_hint_is_printed(self):
        self.assertIn("more goods here would cut the fees by", self.solve())

    def test_show_marks_the_standing_candidate(self):
        table = self.run_command(cli.show, ref=None)
        self.assertIn("*1  Chocolate milk 200ml", table)
        self.assertIn(" 2  Milk 1L", table)
        self.assertIn("-  nothing found", table)

    def test_platform_pricing_replaces_the_planning_fees(self):
        cli.PLATFORMS["beta"] = SimpleNamespace(quote=lambda store, lines, lat, lon: [("Delivery (1 km)", 199), ("Bag", 20)])
        report = self.solve(max_stores=1, top=1)
        self.assertIn("goods 27.50 + Delivery (1 km) 1.99 + Bag 0.20 = 29.69  (priced by Beta)", report)
        self.assertIn("1. 29.69 in 1 order", report)

    def test_failed_platform_pricing_keeps_the_planning_fees_and_says_so(self):
        def refuse(store, lines, lat, lon):
            raise RuntimeError("HTTP 503")
        cli.PLATFORMS["beta"] = SimpleNamespace(quote=refuse)
        report = self.solve(max_stores=1, top=1)
        self.assertIn("! Beta did not price this basket (RuntimeError: HTTP 503)", report)
        self.assertIn("1. about 30.00 in 1 order", report)

    def test_estimated_and_partial_fees_mark_the_total(self):
        self.change(lambda run: run["stores"]["b1"].update(caveat="built from published parameters"))
        self.assertIn("1. about 30.00 in 1 order", self.solve(max_stores=1, top=1))
        self.change(lambda run: run["stores"]["b1"].update(caveat="delivery price only", partial=True))
        report = self.solve(max_stores=1, top=1)
        self.assertIn("1. at least 30.00 in 1 order", report)
        self.assertIn("(delivery price only)", report)


if __name__ == "__main__":
    unittest.main()
