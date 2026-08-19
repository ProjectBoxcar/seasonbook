"""Gold numbers from the real 74-certificate herd. Fail if identity merge regresses."""

from __future__ import annotations

import unittest
from pathlib import Path

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

    def test_last_blood_finds_irreplaceable(self):
        lb = self.snap.last_blood
        self.assertGreater(lb.n_last_founders, 0)
        self.assertGreater(lb.n_irreplaceable, 0)
        self.assertTrue(lb.cards)
        self.assertTrue(self.snap.erosion.summary)

    def test_habit_is_hotter_than_rotation(self):
        e = self.snap.erosion
        rot_y1 = e.rotation[0].mean_f
        hab_y1 = e.habit[0].mean_f
        self.assertGreaterEqual(hab_y1, rot_y1 - 1e-9)

    def test_rescue_books_last_carrier_sires(self):
        used = {a.sire_name.upper() for a in self.snap.plan.assignments}
        self.assertIn("SNOWMASS MATRIX", used)
        rescued = [a for a in self.snap.plan.assignments if a.reason.startswith("rescue:")]
        self.assertGreaterEqual(len(rescued), 4)
        sitting_sires = [c for c in self.snap.last_blood.sitting_out if c.sex == "M"]
        self.assertEqual(sitting_sires, [])

    def test_csv_has_three_years_and_rescues(self):
        import tempfile

        from seasonbook.export import plan_rows, write_plan_csv

        rows = plan_rows(self.snap)
        years = {int(r["year"]) for r in rows}
        self.assertEqual(years, {1, 2, 3})
        y1 = [r for r in rows if int(r["year"]) == 1]
        self.assertEqual(len(y1), 48)
        self.assertGreaterEqual(sum(1 for r in y1 if r["rescue"] == "R"), 4)
        self.assertTrue(any("MATRIX" in r["sire"].upper() for r in y1))
        path = write_plan_csv(self.snap, Path(tempfile.mkdtemp()))
        text = path.read_text(encoding="utf-8")
        self.assertIn("year,dam,sire,f_pct", text)

    def test_board_pdf_is_pdf(self):
        import tempfile

        from seasonbook.book import write_board_pdf

        path = write_board_pdf(self.snap, Path(tempfile.mkdtemp()))
        self.assertTrue(path.read_bytes().startswith(b"%PDF"))
        self.assertGreater(path.stat().st_size, 1000)

    def test_horizon_rescues_last_carrier_sires(self):
        from seasonbook.salvage import last_blood

        self.assertEqual(len(self.snap.rotation), 3)
        for plan in self.snap.rotation:
            blood = last_blood(
                self.snap.herd, self.snap.engine, plan, pairs=self.snap.pairs
            )
            sitting = [c.name for c in blood.sitting_out if c.sex == "M"]
            self.assertEqual(sitting, [], msg=f"year {plan.year} still sitting: {sitting}")

    def test_gate_covers_every_registered_animal(self):
        from seasonbook.gate import KEEP, KEEP_UNTIL_WEANING, LET_GO, WAIT

        g = self.snap.gate
        self.assertEqual(
            g.n_keep + g.n_keep_until + g.n_wait + g.n_let_go,
            self.snap.census.n_registered,
        )
        self.assertEqual(len(g.cards), 74)
        verdicts = {KEEP, KEEP_UNTIL_WEANING, WAIT, LET_GO}
        self.assertTrue(all(c.verdict in verdicts for c in g.cards))
        self.assertGreater(g.n_keep + g.n_keep_until, 0)
        self.assertGreater(g.n_let_go, 0)
        self.assertTrue(g.pair_locks)

    def test_gate_sale_is_only_let_go(self):
        from seasonbook.gate import LET_GO

        g = self.snap.gate
        let_go = {c.name for c in g.cards if c.verdict == LET_GO}
        last = {c.name for c in g.cards if c.last_of_now}
        for name in g.suggested_sale.names:
            self.assertIn(name, let_go)
            self.assertNotIn(name, last)
        self.assertFalse(g.suggested_sale.extinct)

    def test_after_cria_duplicates_some_last_founders(self):
        g = self.snap.gate
        self.assertEqual(g.after.n_cria, 48)
        self.assertLess(g.after.n_last_founders_after, g.after.n_last_founders_now)
        self.assertEqual(g.after.n_last_founders_after, 0)
        self.assertEqual(g.n_keep, 0)
        self.assertEqual(g.n_keep_until, 45)
        self.assertGreater(len(g.after.rescued_founders), 0)
        matrix = next(c for c in g.cards if "MATRIX" in c.name.upper())
        self.assertTrue(matrix.in_year1_plan)
        self.assertTrue(matrix.last_of_now)
        self.assertIn(matrix.verdict, {"KEEP", "KEEP_UNTIL_WEANING"})

    def test_gate_pdf_and_csv(self):
        import tempfile

        from seasonbook.book import write_gate_pdf
        from seasonbook.export import gate_rows, write_gate_csv

        rows = gate_rows(self.snap)
        self.assertEqual(len(rows), 74)
        self.assertTrue(any(r["verdict"] == "LET_GO" for r in rows))
        tmp = Path(tempfile.mkdtemp())
        csv_path = write_gate_csv(self.snap, tmp)
        self.assertIn("verdict", csv_path.read_text(encoding="utf-8").splitlines()[0])
        pdf_path = write_gate_pdf(self.snap, tmp)
        self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF"))
        self.assertGreater(pdf_path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
