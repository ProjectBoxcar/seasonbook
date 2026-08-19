"""CSV / tonight briefing — what the farm pastes into a sheet or reads aloud."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from .pipeline import DEFAULT_OUT, Snapshot


def plan_rows(snap: Snapshot) -> list[dict]:
    plans = list(snap.rotation) or [snap.plan]
    pair_ix = {(p.dam_id, p.sire_id): p for p in snap.pairs}
    rows: list[dict] = []
    for plan in plans:
        for a in plan.assignments:
            pair = pair_ix.get((a.dam_id, a.sire_id))
            rows.append(
                {
                    "year": plan.year,
                    "dam": a.dam_name,
                    "sire": a.sire_name,
                    "f_pct": f"{a.f_pct:.2f}",
                    "verdict": a.verdict,
                    "rescue": "R" if a.reason.startswith("rescue:") else "",
                    "reason": a.reason,
                    "top_ancestor": (pair.top_ancestor if pair else "") or "",
                    "top_contrib_pct": (
                        f"{pair.top_contrib_pct:.1f}" if pair and pair.top_ancestor else ""
                    ),
                }
            )
    return rows


_FIELDS = [
    "year",
    "dam",
    "sire",
    "f_pct",
    "verdict",
    "rescue",
    "reason",
    "top_ancestor",
    "top_contrib_pct",
]


def plan_csv_text(snap: Snapshot) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(plan_rows(snap))
    return buf.getvalue()


def write_plan_csv(snap: Snapshot, out_dir: Path | None = None) -> Path:
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "SeasonPlan.csv"
    path.write_text(plan_csv_text(snap), encoding="utf-8", newline="\n")
    return path


_GATE_FIELDS = [
    "animal",
    "sex",
    "verdict",
    "mk_pct",
    "uniqueness_pct",
    "booked",
    "booked_as",
    "last_of_now",
    "last_of_after",
    "duplicated_by_cria",
    "extinct_if_sold",
    "ne_delta_if_sold",
    "why",
]


def gate_rows(snap: Snapshot) -> list[dict]:
    rows: list[dict] = []
    for c in snap.gate.cards:
        rows.append(
            {
                "animal": c.name,
                "sex": c.sex or "",
                "verdict": c.verdict,
                "mk_pct": f"{c.mk_pct:.2f}",
                "uniqueness_pct": f"{c.uniqueness_pct:.2f}",
                "booked": "Y" if c.in_year1_plan else "",
                "booked_as": c.booked_as,
                "last_of_now": "; ".join(c.last_of_now),
                "last_of_after": "; ".join(c.last_of_after),
                "duplicated_by_cria": "; ".join(c.duplicated_by_cria),
                "extinct_if_sold": "; ".join(c.extinct_if_sold),
                "ne_delta_if_sold": f"{c.ne_delta_if_sold:+.1f}",
                "why": c.why,
            }
        )
    return rows


def gate_csv_text(snap: Snapshot) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_GATE_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(gate_rows(snap))
    return buf.getvalue()


def write_gate_csv(snap: Snapshot, out_dir: Path | None = None) -> Path:
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "TheGate.csv"
    path.write_text(gate_csv_text(snap), encoding="utf-8", newline="\n")
    return path


_WEAN_FIELDS = [
    "cria",
    "dam",
    "sire",
    "f_pct",
    "must_stay",
    "sellable",
    "n_covers",
    "covers",
    "uniqueness_pct",
    "why",
]


def wean_rows(snap: Snapshot) -> list[dict]:
    rows: list[dict] = []
    for c in snap.wean.stay:
        rows.append(
            {
                "cria": c.name,
                "dam": c.dam_name,
                "sire": c.sire_name,
                "f_pct": f"{c.f_pct:.2f}",
                "must_stay": "Y" if c.must_stay else "",
                "sellable": "Y" if c.sellable else "",
                "n_covers": str(c.n_covers),
                "covers": "; ".join(c.covers),
                "uniqueness_pct": f"{c.uniqueness_pct:.2f}",
                "why": c.why,
            }
        )
    return rows


def wean_csv_text(snap: Snapshot) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_WEAN_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(wean_rows(snap))
    return buf.getvalue()


def write_wean_csv(snap: Snapshot, out_dir: Path | None = None) -> Path:
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "WeaningLedger.csv"
    path.write_text(wean_csv_text(snap), encoding="utf-8", newline="\n")
    return path


def tonight_lines(snap: Snapshot) -> list[str]:
    b = snap.briefing()
    plan = snap.plan
    rescued = [a for a in plan.assignments if a.reason.startswith("rescue:")]
    g = snap.gate
    lines = [
        f"TONIGHT  ·  year 1  ·  {len(plan.assignments)} bookings  ·  "
        f"mean F {plan.mean_f*100:.2f}%",
        f"  nucleus  {b['registered']} registered  ·  {b['dams']} dams × {b['sires']} sires",
        f"  close kin  {b['blocks']} BLOCK  ·  last blood  {b['irreplaceable']} irreplaceable",
        f"  rescue into year 1  {len(rescued)}",
        f"  the gate  {g.n_keep} KEEP  ·  {g.n_keep_until} KEEP UNTIL WEANING  ·  "
        f"{g.n_wait} WAIT  ·  {g.n_let_go} LET GO",
        f"  pair-locks  {len(g.pair_locks)}  ·  after cria last founders "
        f"{g.after.n_last_founders_now} → {g.after.n_last_founders_after}",
    ]
    if g.suggested_sale.names:
        lines.append("  suggested sale  " + ", ".join(g.suggested_sale.names))
    w = snap.wean
    lines.append(
        f"  wean  keep {w.n_cover} cria  ·  {w.n_release} parents may list  ·  "
        f"{w.n_sellable_cria} sellable weanlings"
    )
    nxt = snap.nxt
    lines.append(
        f"  next  {nxt.n_collisions} collisions  ·  "
        f"band {nxt.band.n} living Y2={nxt.band.n_year2}  ·  "
        f"shrink {nxt.shrink.n} living Y2={nxt.shrink.n_year2}"
    )
    for c in w.cover[:6]:
        lines.append(f"    stay  {c.name}  ({c.n_covers} last founders)")
    for a in rescued:
        lines.append(f"  R  {a.dam_name}  ×  {a.sire_name}  F={a.f_pct:.2f}%")
        lines.append(f"      {a.reason}")
    if snap.audit.blocks:
        lines.append("  do not book (first 8 BLOCK)")
        for p in snap.audit.blocks[:8]:
            tag = (p.structural or "close kin").replace("_", " ")
            lines.append(
                f"    {p.dam_name}  ×  {p.sire_name}  F={p.f_pct:.2f}%  {tag}"
            )
    return lines
