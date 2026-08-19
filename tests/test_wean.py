"""Weaning Ledger on a toy nucleus. No certificates required."""

from __future__ import annotations

import unittest

from seasonbook.gate import KEEP_UNTIL_WEANING, the_gate
from seasonbook.plan import SeasonPlan
from seasonbook.wean import weaning_ledger

from tests.test_gate import _book, _toy


class WeanToy(unittest.TestCase):
    def _booked(self):
        herd, eng = _toy()
        plan = SeasonPlan(
            year=1,
            assignments=[
                _book(herd, "RARE", "FRESH"),
                _book(herd, "HOT_SIB", "HOT"),
            ],
            unassigned=[],
            mean_f=0.0,
            used_sires={"Fresh Sire": 1, "Hot Sire": 1},
            bench=[],
        )
        gate = the_gate(herd, eng, plan)
        ledger = weaning_ledger(herd, eng, plan, gate)
        return herd, eng, plan, gate, ledger

    def test_one_cria_covers_rare_and_fresh_last_blood(self):
        _, _, _, _, ledger = self._booked()
        cover_names = {c.name for c in ledger.cover}
        self.assertIn("Rare Dam × Fresh Sire", cover_names)
        rare_cria = next(c for c in ledger.stay if c.name == "Rare Dam × Fresh Sire")
        self.assertTrue(rare_cria.must_stay)
        self.assertIn("Unique Blood", rare_cria.covers)
        self.assertGreaterEqual(rare_cria.n_covers, 2)

    def test_common_blood_cria_is_sellable_weanling(self):
        _, _, _, _, ledger = self._booked()
        common = next(c for c in ledger.stay if c.name == "Hot Sib × Hot Sire")
        self.assertTrue(common.sellable)
        self.assertFalse(common.must_stay)
        self.assertEqual(common.covers, [])

    def test_rare_dam_may_leave_if_cover_stays(self):
        _, _, _, gate, ledger = self._booked()
        rare = next(c for c in gate.cards if c.name == "Rare Dam")
        self.assertEqual(rare.verdict, KEEP_UNTIL_WEANING)
        rel = next(r for r in ledger.releases if r.name == "Rare Dam")
        self.assertTrue(rel.may_sell_after_weaning)
        self.assertTrue(any("Rare Dam × Fresh Sire" in n for n in rel.keep_cria + rel.cria_names))

    def test_disaster_if_parent_and_cria_both_leave(self):
        _, _, _, _, ledger = self._booked()
        hit = next(d for d in ledger.disaster if d.parent_name == "Rare Dam")
        self.assertIn("Unique Blood", hit.extinct)

    def test_cover_is_smaller_than_the_crop(self):
        _, _, _, _, ledger = self._booked()
        self.assertEqual(ledger.n_cria, 2)
        self.assertEqual(ledger.n_cover, 1)
        self.assertEqual(ledger.n_sellable_cria, 1)
        self.assertNotIn("Unique Blood", ledger.uncovered)

    def test_unbooked_last_carrier_is_uncovered(self):
        herd, eng = _toy()
        gate = the_gate(herd, eng, plan=None)
        ledger = weaning_ledger(herd, eng, None, gate)
        self.assertEqual(ledger.n_cria, 0)
        self.assertGreater(ledger.n_uncovered, 0)
        self.assertIn("Unique Blood", ledger.uncovered)


if __name__ == "__main__":
    unittest.main()
