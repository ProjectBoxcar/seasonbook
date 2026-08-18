"""Write the certificate nucleus into a minimal AlpacaManager-shaped SQLite.

Does not touch alpaca_demo.db. The live app reads SQLite after a certificate
import; this file is that import, offline, so /api/seasonbook/sync can be
proven on the real 74 before anyone uploads PDFs one by one.

Tables match what backend_api/seasonbook/sync.py reads:
  alpacas(id, name, registration_number, gender, color, sire_id, dam_id,
          sire_is_ancestor, dam_is_ancestor, is_external_sire)
  pedigree_ancestors(id, name, registration_number, gender, color, sire_id, dam_id)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .parse import HerdGraph, ingest_dir
from .pipeline import DEFAULT_CERT_DIR, DEFAULT_OUT

SCHEMA = """
CREATE TABLE IF NOT EXISTS alpacas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    registration_number TEXT,
    gender TEXT,
    color TEXT,
    sire_id INTEGER,
    dam_id INTEGER,
    sire_is_ancestor INTEGER DEFAULT 0,
    dam_is_ancestor INTEGER DEFAULT 0,
    is_external_sire INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pedigree_ancestors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    registration_number TEXT,
    gender TEXT,
    color TEXT,
    sire_id INTEGER,
    dam_id INTEGER
);
"""


class SqliteHerdDB:
    """Duck-typed like clean_database.Database for herd_from_db."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    def get_all_alpacas(self, include_external_sires: bool = True) -> list[dict]:
        if include_external_sires:
            self.cursor.execute("SELECT * FROM alpacas ORDER BY name")
        else:
            self.cursor.execute(
                "SELECT * FROM alpacas WHERE is_external_sire = 0 ORDER BY name"
            )
        return [dict(r) for r in self.cursor.fetchall()]

    def get_alpaca(self, alpaca_id: int) -> dict | None:
        self.cursor.execute("SELECT * FROM alpacas WHERE id = ?", (alpaca_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        self.conn.close()


def _gender(sex: str | None) -> str | None:
    if sex == "F":
        return "Female"
    if sex == "M":
        return "Male"
    return None


def seed_sqlite(
    dest: Path,
    herd: HerdGraph | None = None,
    cert_dir: Path | None = None,
) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    if herd is None:
        herd = ingest_dir(Path(cert_dir) if cert_dir else DEFAULT_CERT_DIR)

    conn = sqlite3.connect(str(dest))
    conn.executescript(SCHEMA)

    anc_pk: dict[str, int] = {}
    for key, node in herd.animals.items():
        cur = conn.execute(
            """
            INSERT INTO pedigree_ancestors (name, registration_number, gender, color)
            VALUES (?, ?, ?, ?)
            """,
            (node.name, node.ar, _gender(node.sex), node.color),
        )
        anc_pk[key] = int(cur.lastrowid)

    for key, node in herd.animals.items():
        conn.execute(
            "UPDATE pedigree_ancestors SET sire_id = ?, dam_id = ? WHERE id = ?",
            (anc_pk.get(node.sire_key) if node.sire_key else None,
             anc_pk.get(node.dam_key) if node.dam_key else None,
             anc_pk[key]),
        )

    registered = set(herd.registered_ids)
    am_pk: dict[str, int] = {}
    for key in herd.registered_ids:
        node = herd.animals[key]
        cur = conn.execute(
            """
            INSERT INTO alpacas
                (name, registration_number, gender, color, is_external_sire)
            VALUES (?, ?, ?, ?, 0)
            """,
            (node.name, node.ar, _gender(node.sex), node.color),
        )
        am_pk[key] = int(cur.lastrowid)

    for key in herd.registered_ids:
        node = herd.animals[key]
        sire_owned = bool(node.sire_key and node.sire_key in registered)
        dam_owned = bool(node.dam_key and node.dam_key in registered)
        sire_id = am_pk.get(node.sire_key) if sire_owned else anc_pk.get(node.sire_key or "")
        dam_id = am_pk.get(node.dam_key) if dam_owned else anc_pk.get(node.dam_key or "")
        conn.execute(
            """
            UPDATE alpacas
               SET sire_id = ?, dam_id = ?,
                   sire_is_ancestor = ?, dam_is_ancestor = ?
             WHERE id = ?
            """,
            (
                sire_id,
                dam_id,
                0 if sire_owned else 1 if sire_id else 0,
                0 if dam_owned else 1 if dam_id else 0,
                am_pk[key],
            ),
        )

    conn.commit()
    conn.close()
    return dest


def default_nucleus_path() -> Path:
    return DEFAULT_OUT / "nucleus.db"
