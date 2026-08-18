"""Seed an AM-shaped SQLite from the 74 certificates and round-trip it."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from seasonbook.pipeline import DEFAULT_CERT_DIR, build_from_herd
from seasonbook.seed_am import SqliteHerdDB, seed_sqlite
from seasonbook.wright import structural_relationship


@unittest.skipUnless(DEFAULT_CERT_DIR.is_dir(), "certificate directory not present")
class SeededSqliteGold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp())
        cls.path = seed_sqlite(cls.tmpdir / "nucleus.db")
        cls.db = SqliteHerdDB(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_owned_count_and_sex(self):
        owned = self.db.get_all_alpacas()
        self.assertEqual(len(owned), 74)
        self.assertTrue(all(r.get("gender") in {"Female", "Male"} for r in owned))

    def test_aftershock_sire_is_owned_alydar(self):
        owned = self.db.get_all_alpacas()
        after = next(r for r in owned if "AFTERSHOCK" in r["name"].upper())
        aly = next(
            r
            for r in owned
            if "ALYDAR" in r["name"].upper() and "AFTERSHOCK" not in r["name"].upper()
        )
        self.assertEqual(after["sire_id"], aly["id"])
        self.assertFalse(after["sire_is_ancestor"])
        self.assertEqual(str(aly["registration_number"]), "35489856")

    def test_sync_roundtrip_is_parent_offspring(self):
        # Import here so the test still runs if AM is not on sys.path.
        import sys

        am_root = Path(__file__).resolve().parents[2] / "AlpacaManager"
        if am_root.is_dir() and str(am_root) not in sys.path:
            sys.path.insert(0, str(am_root))
        from backend_api.seasonbook.sync import herd_from_db

        herd, am_map = herd_from_db(self.db)
        self.assertEqual(len(herd.registered_ids), 74)
        unsexed = [k for k in herd.registered_ids if herd.animals[k].sex not in {"M", "F"}]
        self.assertEqual(unsexed, [])
        aftershock = next(
            a for a in herd.animals.values() if a.registered and "AFTERSHOCK" in a.name.upper()
        )
        alydar = next(
            a
            for a in herd.animals.values()
            if a.am_id
            and "ALYDAR" in a.name.upper()
            and "AFTERSHOCK" not in a.name.upper()
        )
        self.assertEqual(alydar.key, "AR:35489856")
        self.assertEqual(aftershock.sire_key, alydar.key)
        self.assertIn(aftershock.key, am_map)
        self.assertIn(alydar.key, am_map)
        snap = build_from_herd(herd, source_label="seeded-sqlite")
        tag = structural_relationship(aftershock.key, alydar.key, snap.engine.pedigree)
        self.assertEqual(tag, "parent_offspring")
        pair = next(
            p
            for p in snap.pairs
            if p.dam_id == aftershock.key and p.sire_id == alydar.key
        )
        self.assertEqual(pair.verdict, "BLOCK")
        self.assertGreaterEqual(pair.F, 0.25)


if __name__ == "__main__":
    unittest.main()
