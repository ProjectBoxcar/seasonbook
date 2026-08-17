"""Season assignment, close-kin audit, coverage, and three-season rotation.

The assigner is greedy and deterministic:
  1. Never assign BLOCK (F ≥ 20% or structural parent/offspring / full-sib).
  2. Prefer PROCEED over CONFIRM.
  3. Among legal pairs, minimise offspring F, then sire mean kinship.
  4. Dams with the fewest legal sires are placed first (bottleneck first).
  5. Each sire has a capacity cap (default 4).

A 100% legal sire can still sit on the bench: capacity fills with
fresher (lower MK) sires first. That is a feature, not a bug — it is
why Matrix can cover 49/49 and still not appear in the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .parse import HerdGraph
from .wright import (
    WrightEngine,
    structural_relationship,
    verdict_for,
    wright_paths,
)


@dataclass
class Pair:
    dam_id: str
    sire_id: str
    dam_name: str
    sire_name: str
    F: float
    f_pct: float
    verdict: str
    structural: str | None
    top_ancestor: str | None
    top_contrib_pct: float
    score: float


@dataclass
class Assignment:
    dam_id: str
    sire_id: str
    dam_name: str
    sire_name: str
    F: float
    f_pct: float
    verdict: str
    reason: str
    year: int = 1


@dataclass
class SeasonPlan:
    year: int
    assignments: list[Assignment]
    unassigned: list[str]
    mean_f: float
    used_sires: dict[str, int]
    bench: list[dict]


@dataclass
class Audit:
    pairs: list[Pair]
    n_block: int
    n_confirm: int
    n_proceed: int
    blocks: list[Pair]
    confirms: list[Pair]


@dataclass
class CoverRow:
    sire_id: str
    sire_name: str
    mk: float
    mk_pct: float
    legal: int
    block: int
    confirm: int
    proceed: int
    assigned: int
    why: str


def _pair(
    herd: HerdGraph,
    engine: WrightEngine,
    dam_id: str,
    sire_id: str,
    sire_mk: float,
) -> Pair:
    dam = herd.animals[dam_id]
    sire = herd.animals[sire_id]
    f = engine.offspring_f(dam_id, sire_id)
    structural = structural_relationship(dam_id, sire_id, engine.pedigree)
    verdict = verdict_for(f, structural)
    _, hits = wright_paths(dam_id, sire_id, engine.pedigree, engine.max_gen, engine)
    top_name = None
    top_pct = 0.0
    if hits and f > 1e-9:
        anc = herd.animals.get(hits[0].ancestor_id)
        top_name = anc.name if anc else hits[0].ancestor_id
        top_pct = round(100.0 * hits[0].contribution / f, 1)
    # Lower is better. CONFIRM is taxed so PROCEED wins when F is close.
    tax = 0.0 if verdict == "PROCEED" else 0.08 if verdict == "CONFIRM" else 9.0
    score = f + 0.45 * sire_mk + tax
    return Pair(
        dam_id=dam_id,
        sire_id=sire_id,
        dam_name=dam.name,
        sire_name=sire.name,
        F=f,
        f_pct=round(f * 100.0, 2),
        verdict=verdict,
        structural=structural,
        top_ancestor=top_name,
        top_contrib_pct=top_pct,
        score=score,
    )


def all_pairs(herd: HerdGraph, engine: WrightEngine) -> list[Pair]:
    dams = [i for i in herd.registered_ids if herd.animals[i].sex == "F"]
    sires = [i for i in herd.registered_ids if herd.animals[i].sex == "M"]
    mk = {s: engine.mean_kinship(s, herd.registered_ids) for s in sires}
    out: list[Pair] = []
    for d in dams:
        for s in sires:
            out.append(_pair(herd, engine, d, s, mk[s]))
    return out


def audit_pairs(pairs: list[Pair]) -> Audit:
    blocks = [p for p in pairs if p.verdict == "BLOCK"]
    confirms = [p for p in pairs if p.verdict == "CONFIRM"]
    proceed = [p for p in pairs if p.verdict == "PROCEED"]
    blocks.sort(key=lambda p: -p.F)
    confirms.sort(key=lambda p: -p.F)
    return Audit(
        pairs=pairs,
        n_block=len(blocks),
        n_confirm=len(confirms),
        n_proceed=len(proceed),
        blocks=blocks,
        confirms=confirms,
    )


def assign_season(
    pairs: list[Pair],
    herd: HerdGraph,
    engine: WrightEngine,
    capacity: int = 4,
    year: int = 1,
    banned_sires: set[str] | None = None,
    prefer_unused: set[str] | None = None,
) -> SeasonPlan:
    banned = banned_sires or set()
    prefer = prefer_unused or set()
    dams = sorted({p.dam_id for p in pairs})
    sires = sorted({p.sire_id for p in pairs})
    by_dam: dict[str, list[Pair]] = {d: [] for d in dams}
    for p in pairs:
        if p.sire_id in banned:
            continue
        by_dam[p.dam_id].append(p)

    def legal_count(dam_id: str) -> int:
        return sum(1 for p in by_dam[dam_id] if p.verdict != "BLOCK")

    order = sorted(dams, key=lambda d: (legal_count(d), herd.animals[d].name))
    used: dict[str, int] = {s: 0 for s in sires}
    assigned: list[Assignment] = []
    unassigned: list[str] = []

    for dam_id in order:
        candidates = [p for p in by_dam[dam_id] if p.verdict != "BLOCK"]
        # Prefer sires still under capacity
        open_c = [p for p in candidates if used[p.sire_id] < capacity]
        pool = open_c or []
        if not pool:
            unassigned.append(herd.animals[dam_id].name)
            continue
        # Year 2/3: slight bonus to sires not yet used this horizon
        def key(p: Pair) -> tuple:
            unused_bonus = -0.02 if p.sire_id in prefer else 0.0
            return (p.score + unused_bonus, p.F, p.sire_name)

        pick = min(pool, key=key)
        used[pick.sire_id] += 1
        why = _reason(pick)
        assigned.append(
            Assignment(
                dam_id=pick.dam_id,
                sire_id=pick.sire_id,
                dam_name=pick.dam_name,
                sire_name=pick.sire_name,
                F=pick.F,
                f_pct=pick.f_pct,
                verdict=pick.verdict,
                reason=why,
                year=year,
            )
        )

    mean_f = sum(a.F for a in assigned) / len(assigned) if assigned else 0.0
    used_sires = {herd.animals[s].name: n for s, n in used.items() if n}
    bench = _bench(pairs, herd, engine, used, capacity)
    assigned.sort(key=lambda a: (a.sire_name, a.dam_name))
    return SeasonPlan(
        year=year,
        assignments=assigned,
        unassigned=unassigned,
        mean_f=mean_f,
        used_sires=used_sires,
        bench=bench,
    )


def _reason(p: Pair) -> str:
    bits = [f"F={p.f_pct:.2f}% {p.verdict}"]
    if p.structural:
        bits.append(p.structural.replace("_", " "))
    if p.top_ancestor and p.F >= 0.01:
        bits.append(f"pushed by {p.top_ancestor} ({p.top_contrib_pct:.0f}% of F)")
    elif p.F < 0.01:
        bits.append("no close common ancestor in the recorded pedigree")
    return "; ".join(bits)


def _bench(
    pairs: list[Pair],
    herd: HerdGraph,
    engine: WrightEngine,
    used: dict[str, int],
    capacity: int,
) -> list[dict]:
    sires = sorted({p.sire_id for p in pairs})
    rows = []
    n_dams = len({p.dam_id for p in pairs}) or 1
    for s in sires:
        if used.get(s, 0) > 0:
            continue
        mine = [p for p in pairs if p.sire_id == s]
        legal = sum(1 for p in mine if p.verdict != "BLOCK")
        blocks = sum(1 for p in mine if p.verdict == "BLOCK")
        mk = engine.mean_kinship(s, herd.registered_ids)
        if legal == n_dams:
            why = (
                f"Legal on every dam ({legal}/{n_dams}). "
                "Sat out because lower-MK sires filled capacity first — not because of F."
            )
        elif blocks:
            why = f"Legal on {legal}/{n_dams}; {blocks} BLOCK. Unused after fresher sires took the open slots."
        else:
            why = f"Legal on {legal}/{n_dams}. Unused after capacity filled."
        rows.append(
            {
                "sire_id": s,
                "sire_name": herd.animals[s].name,
                "mk_pct": round(mk * 100.0, 2),
                "legal": legal,
                "block": blocks,
                "assigned": 0,
                "why": why,
            }
        )
    rows.sort(key=lambda r: (-r["legal"], r["mk_pct"]))
    return rows


def coverage_table(
    pairs: list[Pair],
    herd: HerdGraph,
    engine: WrightEngine,
    plan: SeasonPlan,
) -> list[CoverRow]:
    assigned_count: dict[str, int] = {}
    for a in plan.assignments:
        assigned_count[a.sire_id] = assigned_count.get(a.sire_id, 0) + 1
    sires = sorted({p.sire_id for p in pairs}, key=lambda s: herd.animals[s].name)
    n_dams = len({p.dam_id for p in pairs}) or 1
    rows: list[CoverRow] = []
    for s in sires:
        mine = [p for p in pairs if p.sire_id == s]
        mk = engine.mean_kinship(s, herd.registered_ids)
        legal = sum(1 for p in mine if p.verdict != "BLOCK")
        block = sum(1 for p in mine if p.verdict == "BLOCK")
        confirm = sum(1 for p in mine if p.verdict == "CONFIRM")
        proceed = sum(1 for p in mine if p.verdict == "PROCEED")
        assigned = assigned_count.get(s, 0)
        if assigned:
            why = f"In the plan ({assigned} dams)."
        elif legal == n_dams:
            why = "100% legal; lost on capacity to lower-MK sires."
        else:
            why = f"{block} BLOCK, {legal} legal; not needed after assignment."
        rows.append(
            CoverRow(
                sire_id=s,
                sire_name=herd.animals[s].name,
                mk=mk,
                mk_pct=round(mk * 100.0, 2),
                legal=legal,
                block=block,
                confirm=confirm,
                proceed=proceed,
                assigned=assigned,
                why=why,
            )
        )
    rows.sort(key=lambda r: (-r.assigned, r.mk_pct))
    return rows


def dam_bottlenecks(pairs: list[Pair], herd: HerdGraph) -> list[dict]:
    dams = sorted({p.dam_id for p in pairs}, key=lambda d: herd.animals[d].name)
    n_sires = len({p.sire_id for p in pairs}) or 1
    rows = []
    for d in dams:
        mine = [p for p in pairs if p.dam_id == d]
        legal = [p for p in mine if p.verdict != "BLOCK"]
        confirm = sum(1 for p in legal if p.verdict == "CONFIRM")
        rows.append(
            {
                "dam_id": d,
                "dam_name": herd.animals[d].name,
                "legal": len(legal),
                "confirm": confirm,
                "block": n_sires - len(legal),
                "tight": len(legal) <= max(3, n_sires // 5),
            }
        )
    rows.sort(key=lambda r: (r["legal"], -r["confirm"], r["dam_name"]))
    return rows


def rotate_three_seasons(
    pairs: list[Pair],
    herd: HerdGraph,
    engine: WrightEngine,
    capacity: int = 4,
) -> list[SeasonPlan]:
    """Year 1 greedy; years 2–3 prefer sires that have not yet worked."""
    y1 = assign_season(pairs, herd, engine, capacity, year=1)
    used = {a.sire_id for a in y1.assignments}
    y2 = assign_season(
        pairs,
        herd,
        engine,
        capacity,
        year=2,
        prefer_unused=set(herd.registered_ids) - used,
    )
    used |= {a.sire_id for a in y2.assignments}
    y3 = assign_season(
        pairs,
        herd,
        engine,
        capacity,
        year=3,
        prefer_unused=set(herd.registered_ids) - used,
    )
    return [y1, y2, y3]


def projected_cria_f(plans: list[SeasonPlan]) -> list[dict]:
    out = []
    for plan in plans:
        if not plan.assignments:
            out.append({"year": plan.year, "mean_f": 0.0, "max_f": 0.0, "n": 0})
            continue
        fs = [a.F for a in plan.assignments]
        out.append(
            {
                "year": plan.year,
                "mean_f": sum(fs) / len(fs),
                "max_f": max(fs),
                "n": len(fs),
            }
        )
    return out
