"""Next Nucleus on a toy herd. No certificates required."""

from __future__ import annotations

import unittest

from seasonbook.gate import LET_GO, WAIT, the_gate
from seasonbook.next import PATH_BAND, PATH_SHRINK, next_nucleus
from seasonbook.plan import SeasonPlan, all_pairs, rotate_from_year1
from seasonbook.wean import weaning_ledger

from tests.test_gate import _book, _toy


class NextToy(unittest.TestCase):
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
        pairs = all_pairs(herd, eng)
        rotation = rotate_from_year1(plan, pairs, herd, eng, capacity=2)
        gate = the_gate(herd, eng, plan)
        wean = weaning_ledger(herd, eng, plan, gate)
        nxt = next_nucleus(herd, eng, plan, rotation, gate, wean, pairs=pairs, capacity=2)
        return herd, eng, plan, gate, wean, nxt

    def test_wait_never_lists(self):
        _, _, _, gate, _, nxt = self._booked()
        wait_names = {c.name for c in gate.cards if c.verdict == WAIT}
        self.assertTrue(wait_names)
        for slot in nxt.calendar:
            if slot.name in wait_names:
                self.assertEqual(slot.window, "HOLD")
                self.assertFalse(slot.path_band)
                self.assertFalse(slot.path_shrink)

    def test_shrink_drops_last_carriers_and_keeps_cover_cria(self):
        _, _, _, _, wean, nxt = self._booked()
        self.assertEqual(nxt.shrink.path, PATH_SHRINK)
        self.assertIn("Rare Dam", nxt.shrink.sold)
        self.assertIn("Fresh Sire", nxt.shrink.sold)
        cover_names = {c.name for c in wean.cover}
        self.assertTrue(cover_names)
        # Covering cria are registered but unsexed, so they count in n_cria.
        self.assertGreaterEqual(nxt.shrink.n_cria, 1)
        self.assertGreater(nxt.shrink.n, 0)

    def test_band_keeps_year1_dams(self):
        _, _, _, _, _, nxt = self._booked()
        self.assertEqual(nxt.band.path, PATH_BAND)
        self.assertIn("Rare Dam", nxt.band.kept)
        self.assertNotIn("Rare Dam", nxt.band.sold)

    def test_hot_sire_can_list_after_covering(self):
        _, _, _, gate, _, nxt = self._booked()
        hot = next(c for c in gate.cards if c.name == "Hot Sire")
        self.assertEqual(hot.verdict, LET_GO)
        slot = next(s for s in nxt.calendar if s.name == "Hot Sire")
        self.assertIn(slot.window, {"AFTER_COVERING", "AFTER_WEANING"})
        self.assertTrue(slot.path_shrink)

    def test_both_paths_have_summaries(self):
        _, _, _, _, _, nxt = self._booked()
        self.assertTrue(nxt.summary)
        self.assertTrue(nxt.band.summary)
        self.assertTrue(nxt.shrink.summary)
        self.assertGreater(nxt.band.n, 0)
        self.assertGreater(nxt.shrink.n, 0)


if __name__ == "__main__":
    unittest.main()
