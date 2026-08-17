"""Gold numbers from the real 74-certificate herd. Fail if identity merge regresses."""

from __future__ import annotations

import unittest

from seasonbook.explain import explain_pair, find_animal
from seasonbook.pipeline import DEFAULT_CERT_DIR, build
from seasonbook.parse import is_junk_name


class JunkNames(unittest.TestCase):
    def test_ocr_crumbs(self):
        self.assertTrue(is_junk_name("a"))
        self.assertTrue(is_junk_name("Pe &"))
        self.assertTrue(is_junk_name("Pa We Ye od"))
        self.assertTrue(is_junk_name("| oY ae"))
        self.assertTrue(is_junk_name("@ \\"))
        self.assertFalse(is_junk_name("TESS"))
        self.assertFalse(is_junk_name("SNOWMASS MATRIX"))
        self.assertFalse(is_junk_name("AUSSIE .38 SPECIAL"))


@unittest.skipUnless(DEFAULT_CERT_DIR.is_dir(), "certificate directory not present")
class RealHerdGold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = build()

    def test_ingest_shape(self):
        b = self.snap.briefing()
        self.assertEqual(b["certificates"], 74)
        self.assertEqual(b["registered"], 74)
        self.assertEqual(b["unsexed"], 0)
        self.assertGreaterEqual(b["animals"], 800)
        self.assertGreaterEqual(b["founders"], 300)
        self.assertGreaterEqual(b["dams"], 45)
        self.assertGreaterEqual(b["sires"], 22)

    def test_no_ocr_founders(self):
        names = {a.name for a in self.snap.herd.animals.values()}
        for junk in ("a", "Pe &", "Pa We Ye od", "oY ae"):
            self.assertNotIn(junk, names)

    def test_paloma_and_wonder_woman(self):
        cards = {c.name: c for c in self.snap.census.cards}
        self.assertAlmostEqual(cards["RR PALOMA PICASSO"].F, 0.0898, places=3)
        self.assertAlmostEqual(cards["RR WONDER WOMAN"].F, 0.0898, places=3)
        self.assertAlmostEqual(cards["SNOWMASS SMOKIN WAVES"].F, 0.0664, places=3)

    def test_aftershock_times_alydar_is_backcross(self):
        herd, eng = self.snap.herd, self.snap.engine
        dam = find_animal(herd, "AFTERSHOCK")
        sire = find_animal(herd, "ALYDAR")
        self.assertIsNotNone(dam)
        self.assertIsNotNone(sire)
        f = eng.offspring_f(dam, sire)
        # Parent × offspring: 25% plus Alydar's own F and any shared ancestors.
        self.assertGreater(f, 0.25)
        self.assertLess(f, 0.27)
        story = explain_pair(herd, eng, "AFTERSHOCK", "ALYDAR")
        self.assertEqual(story["verdict"], "BLOCK")
        self.assertEqual(story["structural"], "parent_offspring")

    def test_inspiration_shogun_full_sibs(self):
        herd, eng = self.snap.herd, self.snap.engine
        a = find_animal(herd, "INSPIRATION")
        b = find_animal(herd, "SHOGUN")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        tag = __import__("seasonbook.wright", fromlist=["structural_relationship"]).structural_relationship
        self.assertEqual(tag(a, b, eng.pedigree), "full_sib")
        self.assertGreaterEqual(eng.offspring_f(a, b), 0.25)

    def test_audit_finds_close_kin(self):
        self.assertGreaterEqual(self.snap.audit.n_block, 10)
        names = {(p.dam_name, p.sire_name) for p in self.snap.audit.blocks}
        joined = " | ".join(d + " x " + s for d, s in names)
        self.assertIn("AFTERSHOCK", joined)
        self.assertIn("ALYDAR", joined)


if __name__ == "__main__":
    unittest.main()
