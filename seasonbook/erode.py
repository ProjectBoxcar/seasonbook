"""Five-year counterfactual: rotation vs barn habit.

Rotation is the existing assigner (low F, low MK, unused sires first).
Habit is what the barn actually does when a famous stallion is legal:
book the hottest (highest mean-kinship) sire still under capacity.

Crias are not treated as instant breeders — they will not cover dams
next year. The comparison is the *cria crop* of each policy: mean F,
founder concentration, and founders present in the living nucleus that
drop to dust in the booked generation.

That is the number the wall should show: follow the famous blood and
these founders leave the next generation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from .census import expected_founder_contributions
from .parse import HerdGraph
from .plan import Assignment, Pair, SeasonPlan, assign_season
from .salvage import MIN_SHARE, _is_real_founder, _name
from .wright import WrightEngine


@dataclass
class YearCrop:
    year: int
    policy: str
    n: int
    mean_f: float
    max_f: float
    mean_f_pct: float
    max_f_pct: float
    n_founders: int
    top_founder: str | None
    top_share_pct: float
    top5_share_pct: float
    used_sires: dict[str, int]


@dataclass
class LostFounder:
    founder_id: str
    founder_name: str
    nucleus_share_pct: float
    rotation_share_pct: float
    habit_share_pct: float


@dataclass
class Erosion:
    years: int
    rotation: list[YearCrop]
    habit: list[YearCrop]
    lost_to_habit: list[LostFounder]
    saved_by_rotation: list[LostFounder]
    habit_sires: list[str]
    summary: str

    def as_dict(self) -> dict:
        return {
            "years": self.years,
            "rotation": [asdict(y) for y in self.rotation],
            "habit": [asdict(y) for y in self.habit],
            "lost_to_habit": [asdict(x) for x in self.lost_to_habit],
            "saved_by_rotation": [asdict(x) for x in self.saved_by_rotation],
            "habit_sires": self.habit_sires,
            "summary": self.summary,
        }


def assign_habit(
    pairs: list[Pair],
    herd: HerdGraph,
    engine: WrightEngine,
    capacity: int = 4,
    year: int = 1,
) -> SeasonPlan:
    """Book the hottest legal sire still under capacity.

    Score is inverted versus the diversity assigner: high MK is preferred.
    BLOCK is still refused. This is the 'we keep using Matrix' policy.
    """
    dams = sorted({p.dam_id for p in pairs})
    sires = sorted({p.sire_id for p in pairs})
    by_dam: dict[str, list[Pair]] = {d: [] for d in dams}
    for p in pairs:
        by_dam[p.dam_id].append(p)

    def legal_count(dam_id: str) -> int:
        return sum(1 for p in by_dam[dam_id] if p.verdict != "BLOCK")

    order = sorted(dams, key=lambda d: (legal_count(d), herd.animals[d].name))
    used: dict[str, int] = {s: 0 for s in sires}
    assigned = []
    unassigned: list[str] = []

    for dam_id in order:
        open_c = [
            p
            for p in by_dam[dam_id]
            if p.verdict != "BLOCK" and used[p.sire_id] < capacity
        ]
        if not open_c:
            unassigned.append(herd.animals[dam_id].name)
            continue
        # Hottest first (high MK), then lowest F as a tie-break so we do
        # not pretend the barn is random — they still avoid the worst pair.
        pick = max(open_c, key=lambda p: (engine.mean_kinship(p.sire_id, herd.registered_ids), -p.F))
        used[pick.sire_id] += 1
        assigned.append(
            Assignment(
                dam_id=pick.dam_id,
                sire_id=pick.sire_id,
                dam_name=pick.dam_name,
                sire_name=pick.sire_name,
                F=pick.F,
                f_pct=pick.f_pct,
                verdict=pick.verdict,
                reason=f"habit: hottest legal sire (MK-first); F={pick.f_pct:.2f}%",
                year=year,
            )
        )

    mean_f = sum(a.F for a in assigned) / len(assigned) if assigned else 0.0
    used_sires = {herd.animals[s].name: n for s, n in used.items() if n}
    assigned.sort(key=lambda a: (a.sire_name, a.dam_name))
    return SeasonPlan(
        year=year,
        assignments=assigned,
        unassigned=unassigned,
        mean_f=mean_f,
        used_sires=used_sires,
        bench=[],
    )


def rotate_n_seasons(
    pairs: list[Pair],
    herd: HerdGraph,
    engine: WrightEngine,
    capacity: int = 4,
    years: int = 5,
) -> list[SeasonPlan]:
    plans: list[SeasonPlan] = []
    used: set[str] = set()
    for year in range(1, years + 1):
        prefer = set(herd.registered_ids) - used if year > 1 else None
        plan = assign_season(
            pairs,
            herd,
            engine,
            capacity=capacity,
            year=year,
            prefer_unused=prefer,
        )
        plans.append(plan)
        used |= {a.sire_id for a in plan.assignments}
        # After every stallion has worked once, reset so year 4/5 can rotate again.
        if used >= {p.sire_id for p in pairs}:
            used = {a.sire_id for a in plan.assignments}
    return plans


def _crop(
    plan: SeasonPlan,
    herd: HerdGraph,
    policy: str,
    cache: dict[str, dict[str, float]],
    min_share: float,
) -> YearCrop:
    acc: dict[str, float] = defaultdict(float)
    n = len(plan.assignments) or 1
    for a in plan.assignments:
        dam_s = cache.setdefault(a.dam_id, expected_founder_contributions(a.dam_id, herd))
        sire_s = cache.setdefault(a.sire_id, expected_founder_contributions(a.sire_id, herd))
        founders = set(dam_s) | set(sire_s)
        for fid in founders:
            if not _is_real_founder(fid):
                continue
            acc[fid] += 0.5 * dam_s.get(fid, 0.0) + 0.5 * sire_s.get(fid, 0.0)
    mean = {fid: val / n for fid, val in acc.items()}
    ranked = sorted(mean.items(), key=lambda kv: -kv[1])
    kept = [(fid, v) for fid, v in ranked if v >= min_share]
    top_id, top_v = (kept[0] if kept else (None, 0.0))
    top5 = sum(v for _, v in kept[:5])
    fs = [a.F for a in plan.assignments]
    return YearCrop(
        year=plan.year,
        policy=policy,
        n=len(plan.assignments),
        mean_f=sum(fs) / len(fs) if fs else 0.0,
        max_f=max(fs) if fs else 0.0,
        mean_f_pct=round((sum(fs) / len(fs) if fs else 0.0) * 100.0, 2),
        max_f_pct=round((max(fs) if fs else 0.0) * 100.0, 2),
        n_founders=len(kept),
        top_founder=_name(herd, top_id) if top_id else None,
        top_share_pct=round(top_v * 100.0, 2),
        top5_share_pct=round(top5 * 100.0, 2),
        used_sires=dict(plan.used_sires),
    )


def _mean_nucleus_shares(herd: HerdGraph, min_share: float) -> dict[str, float]:
    registered = [rid for rid in herd.registered_ids if rid in herd.animals]
    acc: dict[str, float] = defaultdict(float)
    n = len(registered) or 1
    for rid in registered:
        for fid, val in expected_founder_contributions(rid, herd).items():
            if _is_real_founder(fid):
                acc[fid] += val
    return {fid: val / n for fid, val in acc.items() if val / n >= min_share}


def _crop_shares(
    plans: list[SeasonPlan],
    herd: HerdGraph,
    cache: dict[str, dict[str, float]],
) -> dict[str, float]:
    """Average founder share across every cria of the horizon."""
    acc: dict[str, float] = defaultdict(float)
    n = 0
    for plan in plans:
        for a in plan.assignments:
            n += 1
            dam_s = cache.setdefault(a.dam_id, expected_founder_contributions(a.dam_id, herd))
            sire_s = cache.setdefault(a.sire_id, expected_founder_contributions(a.sire_id, herd))
            for fid in set(dam_s) | set(sire_s):
                if _is_real_founder(fid):
                    acc[fid] += 0.5 * dam_s.get(fid, 0.0) + 0.5 * sire_s.get(fid, 0.0)
    if not n:
        return {}
    return {fid: val / n for fid, val in acc.items()}


def erode(
    pairs: list[Pair],
    herd: HerdGraph,
    engine: WrightEngine,
    capacity: int = 4,
    years: int = 5,
    min_share: float = MIN_SHARE,
) -> Erosion:
    rotation_plans = rotate_n_seasons(pairs, herd, engine, capacity, years)
    habit_plans = [
        assign_habit(pairs, herd, engine, capacity, year=y) for y in range(1, years + 1)
    ]
    cache: dict[str, dict[str, float]] = {}
    rotation_crops = [_crop(p, herd, "rotation", cache, min_share) for p in rotation_plans]
    habit_crops = [_crop(p, herd, "habit", cache, min_share) for p in habit_plans]

    nucleus = _mean_nucleus_shares(herd, min_share)
    rot_share = _crop_shares(rotation_plans, herd, cache)
    hab_share = _crop_shares(habit_plans, herd, cache)

    lost: list[LostFounder] = []
    saved: list[LostFounder] = []
    for fid, nshare in nucleus.items():
        r = rot_share.get(fid, 0.0)
        h = hab_share.get(fid, 0.0)
        row = LostFounder(
            founder_id=fid,
            founder_name=_name(herd, fid),
            nucleus_share_pct=round(nshare * 100.0, 2),
            rotation_share_pct=round(r * 100.0, 2),
            habit_share_pct=round(h * 100.0, 2),
        )
        # Lost under habit: present in nucleus, dust in habit crop.
        if h < min_share:
            lost.append(row)
        # Rotation keeps a founder that habit drops.
        if r >= min_share and h < min_share:
            saved.append(row)
    lost.sort(key=lambda x: -x.nucleus_share_pct)
    saved.sort(key=lambda x: -x.nucleus_share_pct)

    habit_sires = sorted(
        {name for plan in habit_plans for name in plan.used_sires},
    )
    rot_y5 = rotation_crops[-1] if rotation_crops else None
    hab_y5 = habit_crops[-1] if habit_crops else None
    rot_mean = (sum(y.mean_f for y in rotation_crops) / len(rotation_crops)) if rotation_crops else 0.0
    hab_mean = (sum(y.mean_f for y in habit_crops) / len(habit_crops)) if habit_crops else 0.0
    ratio = (hab_mean / rot_mean) if rot_mean > 1e-9 else float("inf")
    summary = (
        f"Over {years} seasons rotation mean cria F is {rot_mean*100:.2f}%. "
        f"Barn habit (hottest legal sire) is {hab_mean*100:.2f}% — "
        f"{ratio:.0f}× higher. "
        f"Habit concentrates the crop in {', '.join(habit_sires[:4])}"
        f"{'…' if len(habit_sires) > 4 else ''}. "
        f"Rotation dilutes every founder on purpose; a high founder count "
        f"under habit is concentration, not diversity."
    )
    return Erosion(
        years=years,
        rotation=rotation_crops,
        habit=habit_crops,
        lost_to_habit=lost,
        saved_by_rotation=saved,
        habit_sires=habit_sires,
        summary=summary,
    )
