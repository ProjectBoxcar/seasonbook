"""Keep / Let Go on a toy nucleus. No certificates required."""

from __future__ import annotations

import unittest

from seasonbook.gate import (
    KEEP,
    KEEP_UNTIL_WEANING,
    LET_GO,
    WAIT,
    explain_leave,
    the_gate,
)
from seasonbook.parse import HerdGraph, RawAnimal
from seasonbook.plan import Assignment, SeasonPlan, all_pairs, assign_season
from seasonbook.wright import WrightEngine


def _add(herd: HerdGraph, key: str, name: str, sex: str | None, sire=None, dam=None, registered=False):
    node = RawAnimal(
        key=key,
        name=name,
        sire_key=sire,
        dam_key=dam,
        sex=sex,
        registered=registered,
    )
    herd.animals[key] = node
    if registered:
        herd.registered_ids.append(key)
    return key


def _toy() -> tuple[HerdGraph, WrightEngine]:
    """Four stories in one barn:

    UNIQUE → RARE is the last carrier (50%).
    PAIR_F → LEFT and RIGHT are the only two carriers (pair-lock).
    COMMON saturates HOT + two common dams (LET GO).
    FRESH is an outcross sire (last of FRESH_S / FRESH_D unless booked).
    """
    herd = HerdGraph()
    _add(herd, "UNIQUE", "Unique Blood", "M")
    _add(herd, "OTHER", "Other Blood", "F")
    _add(herd, "PAIR_F", "Pair Founder", "M")
    _add(herd, "PAIR_MATE", "Pair Mate", "F")
    _add(herd, "COMMON_S", "Common Sire", "M")
    _add(herd, "COMMON_D", "Common Dam", "F")
    _add(herd, "FRESH_S", "Fresh Sire F", "M")
    _add(herd, "FRESH_D", "Fresh Dam F", "F")
    _add(herd, "OTHER2", "Other Two", "F")
    _add(herd, "OTHER3", "Other Three", "M")
    _add(herd, "OTHER4", "Other Four", "F")

    _add(herd, "RARE", "Rare Dam", "F", "UNIQUE", "OTHER", registered=True)
    _add(herd, "LEFT", "Left Twin", "F", "PAIR_F", "PAIR_MATE", registered=True)
    _add(herd, "RIGHT", "Right Twin", "M", "PAIR_F", "PAIR_MATE", registered=True)
    # Three full sibs of the common blood so neither parent is last/rare.
    _add(herd, "HOT", "Hot Sire", "M", "COMMON_S", "COMMON_D", registered=True)
    _add(herd, "HOT_SIB", "Hot Sib", "F", "COMMON_S", "COMMON_D", registered=True)
    _add(herd, "HOT_SIB2", "Hot Sib II", "F", "COMMON_S", "COMMON_D", registered=True)
    _add(herd, "COMMON_DAM", "Common Dam Jr", "F", "COMMON_S", "OTHER4", registered=True)
    _add(herd, "COMMON_DAM2", "Common Dam II", "F", "COMMON_S", "OTHER2", registered=True)
    _add(herd, "FRESH", "Fresh Sire", "M", "FRESH_S", "FRESH_D", registered=True)
    return herd, WrightEngine(herd.to_pedigree(), max_gen=6)


def _book(herd, dam, sire, year=1, reason="seed"):
    return Assignment(dam, sire, herd.animals[dam].name, herd.animals[sire].name, 0.0, 0.0, "PROCEED", reason, year)


class GateToy(unittest.TestCase):
    def test_rare_dam_is_keep_when_unbooked(self):
        herd, eng = _toy()
        gate = the_gate(herd, eng, plan=None)
        rare = next(c for c in gate.cards if c.name == "Rare Dam")
        self.assertEqual(rare.verdict, KEEP)
        self.assertIn("Unique Blood", rare.last_of_now)
        self.assertIn("Unique Blood", rare.last_of_after)
        self.assertIn("Unique Blood", rare.extinct_if_sold)

    def test_booking_rare_dam_makes_keep_until_weaning(self):
        herd, eng = _toy()
        plan = SeasonPlan(
            year=1,
            assignments=[_book(herd, "RARE", "FRESH")],
            unassigned=[],
            mean_f=0.0,
            used_sires={"Fresh Sire": 1},
            bench=[],
        )
        gate = the_gate(herd, eng, plan)
        rare = next(c for c in gate.cards if c.name == "Rare Dam")
        self.assertEqual(rare.verdict, KEEP_UNTIL_WEANING)
        self.assertIn("Unique Blood", rare.last_of_now)
        self.assertNotIn("Unique Blood", rare.last_of_after)
        self.assertIn("Unique Blood", rare.duplicated_by_cria)
        rescued_names = {r.founder_name for r in gate.after.rescued_founders}
        self.assertIn("Unique Blood", rescued_names)

    def test_fresh_sire_keep_until_weaning_when_booked(self):
        herd, eng = _toy()
        plan = SeasonPlan(
            year=1,
            assignments=[_book(herd, "RARE", "FRESH")],
            unassigned=[],
            mean_f=0.0,
            used_sires={"Fresh Sire": 1},
            bench=[],
        )
        gate = the_gate(herd, eng, plan)
        fresh = next(c for c in gate.cards if c.name == "Fresh Sire")
        self.assertEqual(fresh.verdict, KEEP_UNTIL_WEANING)
        self.assertTrue(fresh.last_of_now)
        self.assertFalse(fresh.last_of_after)

    def test_twins_are_wait_and_pair_locked(self):
        herd, eng = _toy()
        gate = the_gate(herd, eng)
        left = next(c for c in gate.cards if c.name == "Left Twin")
        right = next(c for c in gate.cards if c.name == "Right Twin")
        self.assertEqual(left.verdict, WAIT)
        self.assertEqual(right.verdict, WAIT)
        locks = [p for p in gate.pair_locks if p.founder_name == "Pair Founder"]
        self.assertEqual(len(locks), 1)
        names = {locks[0].a_name, locks[0].b_name}
        self.assertEqual(names, {"Left Twin", "Right Twin"})

    def test_selling_left_twin_makes_right_last(self):
        herd, eng = _toy()
        gate = the_gate(herd, eng)
        impact = explain_leave(gate, "Left Twin")
        self.assertIsNotNone(impact)
        self.assertFalse(impact.extinct_founders)
        self.assertTrue(impact.new_last)
        self.assertEqual(impact.new_last[0]["remaining_name"], "Right Twin")
        self.assertEqual(impact.new_last[0]["founder_name"], "Pair Founder")

    def test_hot_sire_is_let_go(self):
        herd, eng = _toy()
        gate = the_gate(herd, eng)
        hot = next(c for c in gate.cards if c.name == "Hot Sire")
        self.assertEqual(hot.verdict, LET_GO)
        self.assertFalse(hot.last_of_now)
        self.assertFalse(hot.rare_of_now)
        self.assertFalse(hot.extinct_if_sold)

    def test_suggested_sale_does_not_touch_last_or_pair_lock(self):
        herd, eng = _toy()
        gate = the_gate(herd, eng)
        banned = {"Rare Dam", "Left Twin", "Right Twin", "Fresh Sire"}
        for name in gate.suggested_sale.names:
            self.assertNotIn(name, banned)
        self.assertFalse(gate.suggested_sale.extinct)

    def test_after_cria_drops_last_founders(self):
        herd, eng = _toy()
        unbooked = the_gate(herd, eng, plan=None)
        plan = SeasonPlan(
            year=1,
            assignments=[
                _book(herd, "RARE", "FRESH"),
                _book(herd, "LEFT", "HOT"),
            ],
            unassigned=[],
            mean_f=0.0,
            used_sires={"Fresh Sire": 1, "Hot Sire": 1},
            bench=[],
        )
        booked = the_gate(herd, eng, plan)
        self.assertLess(
            booked.after.n_last_founders_after,
            unbooked.after.n_last_founders_now,
        )
        self.assertGreaterEqual(booked.after.n_cria, 2)
        self.assertIn("Unique Blood", {r.founder_name for r in booked.after.rescued_founders})

    def test_assigner_plan_is_accepted(self):
        herd, eng = _toy()
        pairs = all_pairs(herd, eng)
        plan = assign_season(pairs, herd, eng, capacity=2)
        gate = the_gate(herd, eng, plan)
        self.assertEqual(
            gate.n_keep + gate.n_keep_until + gate.n_wait + gate.n_let_go,
            len(herd.registered_ids),
        )
        self.assertTrue(gate.summary)


if __name__ == "__main__":
    unittest.main()
