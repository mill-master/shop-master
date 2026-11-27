import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import units  # noqa: E402


class Measure(unittest.TestCase):
    def test_sizes_as_the_three_platforms_write_them(self):
        cases = {
            "Sante Milk 2.5%, 1L": [1000, "ml"],
            "რძე 2.5% /სანტინო/ 950მლ": [950, "ml"],
            "რძე /მილა  2.5% / 1ლ": [1000, "ml"],
            "რძე 3.2% 0,750 ლ/Milk 3.2% 0,750L": [750, "ml"],
            "კვერცხი 1 კატეგორია /დილა/ 10ც": [10, "pc"],
            "კვერცხი /დილა/ M-0 / 15 ცალიანი შეკვრა": [15, "pc"],
            "Eggs / Koda Market 0 categories / 10 pcs": [10, "pc"],
            "პური ხორბლის /ჰარის/470გ": [470, "g"],
            "ბრინჯი გრძელმარცვლიანი 900 გრ N1": [900, "g"],
            "სოსისი \"რძიანი\" ასაწონი 1 კგ": [1000, "g"],
            "Yarmarka Long Rice 5x80g, 400g": [400, "g"],
            "Chocolate/Gunz/Chocolate egg Paw Patrol 48*20g": [960, "g"],
            "Bakhmaro Mineral Water 6 x 1.5 l": [9000, "ml"],
            "Cheese / Valio / Gran Regale 100 g": [100, "g"],
            "Supremo round rice 800 g/4860101960759 1pc": [800, "g"],
            "Kumis egg farmer 1pc/2000002028093": [1, "pc"],
            "Dila egg white 15 pcs/4860007947052": [15, "pc"],
        }
        for name, size in cases.items():
            with self.subTest(name=name):
                self.assertEqual(units.measure(name), size)

    def test_a_size_below_one_gram_or_millilitre_is_a_mislabel_and_no_size(self):
        for name in ("Tabla Saperavi red dry 0.75ml", "Didgori sulguni smoked-0.25g"):
            with self.subTest(name=name):
                self.assertIsNone(units.measure(name))
        self.assertEqual(units.measure("Wine 0.75ml, 750 ml"), [750, "ml"])

    def test_figures_that_are_not_sizes_are_left_alone(self):
        for name in ("Paracetamol 500mg #20", "iPhone 15 128GB", "კვერცხი 0 კატეგორია", "Milk 2.5%", "5 lemons", "E27 lamp", ""):
            with self.subTest(name=name):
                self.assertIsNone(units.measure(name))


class Packs(unittest.TestCase):
    def test_packs_cover_the_amount_asked(self):
        self.assertEqual(units.packs([20, "pc"], [10, "pc"]), 2)
        self.assertEqual(units.packs([20, "pc"], [15, "pc"]), 2)
        self.assertEqual(units.packs([1500, "g"], [500, "g"]), 3)
        self.assertEqual(units.packs([200, "g"], [1000, "g"]), 1)

    def test_a_pack_a_tenth_short_counts_as_the_size_asked(self):
        self.assertEqual(units.packs([1000, "ml"], [950, "ml"]), 1)
        self.assertEqual(units.packs([1000, "g"], [900, "g"]), 1)
        self.assertEqual(units.packs([1000, "g"], [800, "g"]), 2)

    def test_sizes_of_different_kinds_do_not_compare(self):
        self.assertIsNone(units.packs([1000, "ml"], [900, "g"]))
        self.assertIsNone(units.packs([10, "pc"], None))


class PerUnit(unittest.TestCase):
    def test_price_per_kilogram_litre_and_piece(self):
        self.assertEqual(units.per_unit(795, [800, "g"]), (994, "kg"))
        self.assertEqual(units.per_unit(549, [1000, "ml"]), (549, "l"))
        self.assertEqual(units.per_unit(585, [10, "pc"]), (58, "pc"))
        self.assertIsNone(units.per_unit(585, None))


if __name__ == "__main__":
    unittest.main()
