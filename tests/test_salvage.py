"""Last Blood and five-year erosion on a toy nucleus. No certificates required."""

from __future__ import annotations

import unittest

from seasonbook.erode import assign_habit, erode
from seasonbook.parse import HerdGraph, RawAnimal
from seasonbook.plan import Assignment, SeasonPlan, all_pairs, assign_season
from seasonbook.salvage import apply_rescue, last_blood
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
    """RARE uniquely carries UNIQUE. HOT saturates COMMON blood. FRESH is outcross."""
    herd = HerdGraph()
    _add(herd, "UNIQUE", "Unique Blood", "M")
    _add(herd, "OTHER", "Other Blood", "F")
    _add(herd, "COMMON_S", "Common Sire", "M")
    _add(herd, "COMMON_D", "Common Dam", "F")
    _add(herd, "FRESH_S", "Fresh Sire F", "M")
    _add(herd, "FRESH_D", "Fresh Dam F", "F")
    _add(herd, "OTHER2", "Other Two", "F")
    _add(herd, "OTHER3", "Other Three", "M")
    _add(herd, "OTHER4", "Other Four", "F")

    # Registered nucleus
    _add(herd, "RARE", "Rare Dam", "F", "UNIQUE", "OTHER", registered=True)
    _add(herd, "COMMON_DAM", "Common Dam Jr", "F", "COMMON_S", "OTHER4", registered=True)
    _add(herd, "HOT", "Hot Sire", "M", "COMMON_S", "COMMON_D", registered=True)
    _add(herd, "FRESH", "Fresh Sire", "M", "FRESH_S", "FRESH_D", registered=True)
    # A second common dam so habit has capacity to burn on HOT.
    _add(herd, "COMMON_DAM2", "Common Dam II", "F", "COMMON_S", "OTHER2", registered=True)
    return herd, WrightEngine(herd.to_pedigree(), max_gen=6)


class LastBloodToy(unittest.TestCase):
    def test_rare_dam_is_last_carrier_of_unique(self):
        herd, eng = _toy()
        pairs = all_pairs(herd, eng)
        plan = assign_season(pairs, herd, eng, capacity=2)
        blood = last_blood(herd, eng, plan)
        last_names = {f.founder_name for f in blood.last_founders}
        self.assertIn("Unique Blood", last_names)
        rare = next(c for c in blood.cards if c.name == "Rare Dam")
        self.assertTrue(rare.irreplaceable)
        self.assertIn("Unique Blood", rare.last_of)
        self.assertGreater(rare.uniqueness, 0.4)

    def test_hot_sire_is_not_last_of_unique(self):
        herd, eng = _toy()
        blood = last_blood(herd, eng)
        hot = next((c for c in blood.cards if c.name == "Hot Sire"), None)
        if hot:
            self.assertNotIn("Unique Blood", hot.last_of)


class RescueOverlay(unittest.TestCase):
    def test_swaps_one_dam_onto_last_carrier_sire(self):
        herd, eng = _toy()
        pairs = all_pairs(herd, eng)
        # Fabricate a plan that books Hot twice and leaves Fresh (last of
        # Fresh Sire F / Fresh Dam F) on the bench.
        rare = next(p for p in pairs if p.dam_name == "Rare Dam" and p.sire_name == "Hot Sire")
        common = next(
            p for p in pairs if p.dam_name == "Common Dam Jr" and p.sire_name == "Hot Sire"
        )
        common2 = next(
            p for p in pairs if p.dam_name == "Common Dam II" and p.sire_name == "Hot Sire"
        )
        plan = SeasonPlan(
            year=1,
            assignments=[
                Assignment(
                    rare.dam_id, rare.sire_id, rare.dam_name, rare.sire_name,
                    rare.F, rare.f_pct, rare.verdict, "seed", 1,
                ),
                Assignment(
                    common.dam_id, common.sire_id, common.dam_name, common.sire_name,
                    common.F, common.f_pct, common.verdict, "seed", 1,
                ),
                Assignment(
                    common2.dam_id, common2.sire_id, common2.dam_name, common2.sire_name,
                    common2.F, common2.f_pct, common2.verdict, "seed", 1,
                ),
            ],
            unassigned=[],
            mean_f=0.0,
            used_sires={"Hot Sire": 3},
            bench=[],
        )
        blood = last_blood(herd, eng, plan, pairs=pairs)
        fresh = next(c for c in blood.cards if c.name == "Fresh Sire")
        self.assertTrue(fresh.irreplaceable)
        self.assertFalse(fresh.in_year1_plan)
        rescued = apply_rescue(plan, pairs, herd, eng, blood, capacity=4)
        self.assertIn("Fresh Sire", rescued.used_sires)
        self.assertEqual(rescued.used_sires["Fresh Sire"], 1)
        self.assertEqual(sum(rescued.used_sires.values()), 3)
        self.assertTrue(any(a.reason.startswith("rescue:") for a in rescued.assignments))


class ErosionToy(unittest.TestCase):
    def test_habit_prefers_hot_sire(self):
        herd, eng = _toy()
        pairs = all_pairs(herd, eng)
        habit = assign_habit(pairs, herd, eng, capacity=4, year=1)
        used = set(habit.used_sires)
        self.assertIn("Hot Sire", used)

    def test_rotation_can_keep_unique_when_habit_drops_it(self):
        herd, eng = _toy()
        pairs = all_pairs(herd, eng)
        report = erode(pairs, herd, eng, capacity=2, years=3)
        saved = {r.founder_name for r in report.saved_by_rotation}
        # Unique Blood is 50% of Rare Dam and 0% of Hot Sire.
        # Habit books Hot; rotation prefers Fresh (lower MK).
        self.assertTrue(
            "Unique Blood" in saved or report.rotation[-1].n_founders >= report.habit[-1].n_founders,
            msg=report.summary,
        )


if __name__ == "__main__":
    unittest.main()
