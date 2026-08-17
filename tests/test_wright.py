"""Gold-standard Wright/Malécot identities. Independent of certificates."""

from __future__ import annotations

import unittest

from seasonbook.wright import (
    PedigreeNode,
    WrightEngine,
    coancestry,
    expected_offspring_f,
    structural_relationship,
    verdict_for,
    wright_f,
)


def node(i, s=None, d=None, name=""):
    return PedigreeNode(id=i, sire_id=s, dam_id=d, name=name or i)


class WrightIdentities(unittest.TestCase):
    def test_unrelated_founders_zero(self):
        ped = {"A": node("A"), "B": node("B")}
        self.assertEqual(expected_offspring_f("A", "B", ped), 0.0)
        self.assertEqual(wright_f("A", ped), 0.0)

    def test_parent_offspring_is_quarter_regardless_of_id_order(self):
        # F(cria of parent × offspring) = 0.25 when the parent is not inbred
        # and the other parent of the offspring is unrelated.
        for sire_id, dam_id in (("ZZ_SIRE", "AA_DAM"), ("AA_SIRE", "ZZ_DAM")):
            ped = {
                sire_id: node(sire_id),
                "OTHER": node("OTHER"),
                dam_id: node(dam_id, sire_id, "OTHER"),
            }
            f = expected_offspring_f(dam_id, sire_id, ped)
            self.assertAlmostEqual(f, 0.25, places=12, msg=f"{sire_id}×{dam_id}")
            # reverse argument order must match
            f2 = expected_offspring_f(sire_id, dam_id, ped)
            self.assertAlmostEqual(f, f2, places=12)

    def test_full_sibs_quarter(self):
        ped = {
            "S": node("S"),
            "D": node("D"),
            "C1": node("C1", "S", "D"),
            "C2": node("C2", "S", "D"),
        }
        self.assertAlmostEqual(expected_offspring_f("C1", "C2", ped), 0.25, places=12)

    def test_half_sibs_eighth(self):
        ped = {
            "S": node("S"),
            "D1": node("D1"),
            "D2": node("D2"),
            "C1": node("C1", "S", "D1"),
            "C2": node("C2", "S", "D2"),
        }
        self.assertAlmostEqual(expected_offspring_f("C1", "C2", ped), 0.125, places=12)

    def test_inbred_parent_raises_backcross_above_quarter(self):
        # Grandparents are full sibs, so SIRE has F=0.25.
        # f(sire, daughter) = (f(sire,sire) + f(sire, other))/2
        # f(sire,sire) = (1+0.25)/2 = 0.625; f(sire,other)=0 → 0.3125.
        ped = {
            "GF": node("GF"),
            "GM": node("GM"),
            "GS": node("GS", "GF", "GM"),
            "GD": node("GD", "GF", "GM"),
            "SIRE": node("SIRE", "GS", "GD"),
            "OTHER": node("OTHER"),
            "DAU": node("DAU", "SIRE", "OTHER"),
        }
        self.assertAlmostEqual(wright_f("SIRE", ped), 0.25, places=12)
        self.assertAlmostEqual(expected_offspring_f("DAU", "SIRE", ped), 0.3125, places=12)

    def test_self_coancestry(self):
        ped = {"A": node("A")}
        self.assertAlmostEqual(coancestry("A", "A", ped), 0.5, places=12)

    def test_engine_memo_matches_fresh(self):
        ped = {
            "S": node("S"),
            "D": node("D"),
            "C": node("C", "S", "D"),
        }
        eng = WrightEngine(ped)
        self.assertEqual(eng.f("C"), wright_f("C", ped))
        self.assertEqual(eng.offspring_f("S", "D"), 0.0)

    def test_verdicts(self):
        self.assertEqual(verdict_for(0.25, "parent_offspring"), "BLOCK")
        self.assertEqual(verdict_for(0.25, None), "BLOCK")
        self.assertEqual(verdict_for(0.125, "paternal_half_sib"), "CONFIRM")
        self.assertEqual(verdict_for(0.02, None), "PROCEED")

    def test_structural_tags(self):
        ped = {
            "S": node("S"),
            "D": node("D"),
            "C1": node("C1", "S", "D"),
            "C2": node("C2", "S", "D"),
            "H": node("H", "S", "X") if False else node("H", "S", "U"),
            "U": node("U"),
        }
        ped["H"] = node("H", "S", "U")
        self.assertEqual(structural_relationship("S", "C1", ped), "parent_offspring")
        self.assertEqual(structural_relationship("C1", "C2", ped), "full_sib")
        self.assertEqual(structural_relationship("C1", "H", ped), "paternal_half_sib")


if __name__ == "__main__":
    unittest.main()
