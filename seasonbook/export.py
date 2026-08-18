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


def tonight_lines(snap: Snapshot) -> list[str]:
    b = snap.briefing()
    plan = snap.plan
    rescued = [a for a in plan.assignments if a.reason.startswith("rescue:")]
    lines = [
        f"TONIGHT  ·  year 1  ·  {len(plan.assignments)} bookings  ·  "
        f"mean F {plan.mean_f*100:.2f}%",
        f"  nucleus  {b['registered']} registered  ·  {b['dams']} dams × {b['sires']} sires",
        f"  close kin  {b['blocks']} BLOCK  ·  last blood  {b['irreplaceable']} irreplaceable",
        f"  rescue into year 1  {len(rescued)}",
    ]
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
