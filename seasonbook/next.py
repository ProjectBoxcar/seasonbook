"""Next Nucleus — two sale paths, and what the living herd becomes.

The Gate and Weaning Ledger say who *may* leave. They do not say whether
the three-season rotation still exists after they do.

The year-2/3 horizon books the same 48 dams. Selling the 45 KEEP UNTIL
WEANING animals after weaning retires that dam band. That is a choice,
not a bug:

  KEEP_DAM_BAND       keep the 48 year-1 dams. Sell surplus sires the
                      later years do not need. Horizon of 48 bookings lives.
  SHRINK_NUCLEUS      execute The Gate. Covering cria stay. WAIT stay.
                      Year 2 is whatever females remain.
  FINISH_THEN_SHRINK  run years 1–3 as printed. Then sell the SHRINK list.
                      The eight collision sires work first; they leave after
                      year 3. This is the path that does not throw away the
                      board.

Crias are not treated as instant breeders. They join as living carriers
only. Years 2–3 are scored on the adults still registered.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass

from .census import build_census
from .gate import KEEP_UNTIL_WEANING, LET_GO, WAIT, TheGate
from .parse import HerdGraph, RawAnimal
from .plan import SeasonPlan, assign_season
from .salvage import last_blood
from .wean import WeaningLedger
from .wright import WrightEngine


PATH_BAND = "KEEP_DAM_BAND"
PATH_SHRINK = "SHRINK_NUCLEUS"
PATH_FINISH = "FINISH_THEN_SHRINK"


@dataclass
class Collision:
    sire_id: str
    sire_name: str
    years: list[int]
    n_bookings: int
    verdict: str
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SaleSlot:
    animal_id: str
    name: str
    sex: str | None
    verdict: str
    window: str
    path_band: bool
    path_shrink: bool
    path_finish: bool
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Projected:
    path: str
    n: int
    n_dams: int
    n_sires: int
    n_unsexed: int
    n_cria: int
    ne: float
    fge: float
    mean_f_pct: float
    n_last_founders: int
    n_irreplaceable: int
    n_year2: int
    year2_mean_f_pct: float
    year2_unassigned: list[str]
    year2_plan: list[dict]
    kept: list[str]
    sold: list[str]
    summary: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["ne"] = round(self.ne, 1)
        d["fge"] = round(self.fge, 2)
        d["mean_f_pct"] = round(self.mean_f_pct, 2)
        d["year2_mean_f_pct"] = round(self.year2_mean_f_pct, 2)
        return d


@dataclass
class CoreAnimal:
    animal_id: str
    name: str
    sex: str | None
    mk_pct: float
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class NextNucleus:
    collisions: list[Collision]
    calendar: list[SaleSlot]
    core: list[CoreAnimal]
    band: Projected
    shrink: Projected
    finish: Projected
    n_collisions: int
    n_core: int
    summary: str

    def as_dict(self) -> dict:
        return {
            "n_collisions": self.n_collisions,
            "n_core": self.n_core,
            "summary": self.summary,
            "collisions": [c.as_dict() for c in self.collisions],
            "core": [c.as_dict() for c in self.core],
            "calendar": [s.as_dict() for s in self.calendar],
            "band": self.band.as_dict(),
            "shrink": self.shrink.as_dict(),
            "finish": self.finish.as_dict(),
        }


def _clone(herd: HerdGraph) -> HerdGraph:
    return copy.deepcopy(herd)


def _add_cria(herd: HerdGraph, cid: str, dam_id: str, sire_id: str, name: str) -> None:
    if cid in herd.animals:
        herd.animals[cid].registered = True
        if cid not in herd.registered_ids:
            herd.registered_ids.append(cid)
        return
    herd.animals[cid] = RawAnimal(
        key=cid,
        name=name,
        sire_key=sire_id,
        dam_key=dam_id,
        sex=None,
        registered=True,
    )
    herd.registered_ids.append(cid)


def _project_herd(
    herd: HerdGraph,
    engine: WrightEngine,
    keep_ids: list[str],
    cria: list[tuple[str, str, str, str]],
    pairs: list,
    capacity: int,
    banned_sires: set[str],
    path: str,
    sold_names: list[str],
) -> Projected:
    h = _clone(herd)
    for cid, dam_id, sire_id, name in cria:
        _add_cria(h, cid, dam_id, sire_id, name)
    keep = set(keep_ids) | {c[0] for c in cria}
    h.registered_ids = [i for i in h.registered_ids if i in keep]
    # Cria just appended may have been filtered if keep didn't include them —
    # we unioned cria ids into keep, so they stay.
    eng = WrightEngine(h.to_pedigree(), max_gen=engine.max_gen)
    census = build_census(h, eng)
    blood = last_blood(h, eng)
    dams = [i for i in h.registered_ids if h.animals.get(i) and h.animals[i].sex == "F"]
    sires = [i for i in h.registered_ids if h.animals.get(i) and h.animals[i].sex == "M"]
    n_cria = sum(1 for i in h.registered_ids if i.startswith("CRIA:"))
    year2_n = 0
    year2_f = 0.0
    unassigned: list[str] = []
    year2_plan: list[dict] = []
    if dams and sires:
        live_pairs = [
            p
            for p in pairs
            if p.dam_id in set(dams) and p.sire_id in set(sires) and p.sire_id not in banned_sires
        ]
        if live_pairs:
            y2 = assign_season(live_pairs, h, eng, capacity=capacity, year=2)
            year2_n = len(y2.assignments)
            year2_f = y2.mean_f * 100.0
            unassigned = list(y2.unassigned)
            year2_plan = [
                {
                    "dam_name": a.dam_name,
                    "sire_name": a.sire_name,
                    "f_pct": a.f_pct,
                    "verdict": a.verdict,
                    "reason": a.reason,
                }
                for a in y2.assignments
            ]
    kept_names = sorted(
        h.animals[i].name for i in h.registered_ids if i in h.animals and not i.startswith("CRIA:")
    )
    summary = (
        f"{path}: {census.n_registered} living  ·  {census.n_dams} dams × "
        f"{census.n_sires} sires  ·  {n_cria} cria  ·  Ne {census.effective_size:.1f}  ·  "
        f"last founders {blood.n_last_founders}  ·  year-2 bookings {year2_n}"
        + (f"  ·  unassigned {len(unassigned)}" if unassigned else "")
    )
    return Projected(
        path=path,
        n=census.n_registered,
        n_dams=census.n_dams,
        n_sires=census.n_sires,
        n_unsexed=census.n_unsexed,
        n_cria=n_cria,
        ne=census.effective_size,
        fge=census.founder_genome_equivalents,
        mean_f_pct=census.mean_f * 100.0,
        n_last_founders=blood.n_last_founders,
        n_irreplaceable=blood.n_irreplaceable,
        n_year2=year2_n,
        year2_mean_f_pct=year2_f,
        year2_unassigned=unassigned,
        year2_plan=year2_plan,
        kept=kept_names,
        sold=sold_names,
        summary=summary,
    )


def next_nucleus(
    herd: HerdGraph,
    engine: WrightEngine,
    plan: SeasonPlan,
    rotation: list[SeasonPlan],
    gate: TheGate,
    wean: WeaningLedger,
    pairs: list | None = None,
    capacity: int = 4,
) -> NextNucleus:
    pairs = pairs or []
    year1_dams = {a.dam_id for a in plan.assignments}
    year1_sires = {a.sire_id for a in plan.assignments}
    later_sires: dict[str, list[int]] = {}
    later_count: dict[str, int] = {}
    for p in rotation[1:]:
        for a in p.assignments:
            later_sires.setdefault(a.sire_id, [])
            if p.year not in later_sires[a.sire_id]:
                later_sires[a.sire_id].append(p.year)
            later_count[a.sire_id] = later_count.get(a.sire_id, 0) + 1

    by_id = {c.animal_id: c for c in gate.cards}
    extra_cria = [c for c in wean.stay if not c.must_stay and not c.sellable]
    cover_dams = {c.dam_id for c in wean.cover}

    collisions: list[Collision] = []
    for sid, years in later_sires.items():
        card = by_id.get(sid)
        if card is None or card.verdict != LET_GO:
            continue
        name = card.name
        collisions.append(
            Collision(
                sire_id=sid,
                sire_name=name,
                years=sorted(years),
                n_bookings=later_count.get(sid, 0),
                verdict=card.verdict,
                why=(
                    f"{name} is LET GO, but year "
                    f"{'/'.join(str(y) for y in sorted(years))} still books them "
                    f"{later_count.get(sid, 0)}×. Selling this fall kills that horizon row."
                ),
            )
        )
    collisions.sort(key=lambda c: (-c.n_bookings, c.sire_name))

    calendar: list[SaleSlot] = []
    for card in gate.cards:
        in_dam = card.animal_id in year1_dams
        in_sire = card.animal_id in year1_sires
        needed_later = card.animal_id in later_sires
        covering_dam = card.animal_id in cover_dams

        if card.verdict == WAIT:
            calendar.append(
                SaleSlot(
                    animal_id=card.animal_id,
                    name=card.name,
                    sex=card.sex,
                    verdict=card.verdict,
                    window="HOLD",
                    path_band=False,
                    path_shrink=False,
                    path_finish=False,
                    why=f"{card.name} is pair-locked. All three paths keep them. They are the residual nucleus.",
                )
            )
            continue

        if card.verdict == LET_GO and card.sex == "M":
            if needed_later:
                calendar.append(
                    SaleSlot(
                        animal_id=card.animal_id,
                        name=card.name,
                        sex=card.sex,
                        verdict=card.verdict,
                        window="AFTER_WEANING",
                        path_band=False,
                        path_shrink=True,
                        path_finish=True,
                        why=(
                            f"{card.name} is LET GO but years 2–3 still book them. "
                            "KEEP DAM BAND holds them. SHRINK sells after year-1 covering. "
                            "FINISH THEN SHRINK lets them work years 2–3, then lists them."
                        ),
                    )
                )
            else:
                calendar.append(
                    SaleSlot(
                        animal_id=card.animal_id,
                        name=card.name,
                        sex=card.sex,
                        verdict=card.verdict,
                        window="AFTER_COVERING",
                        path_band=True,
                        path_shrink=True,
                        path_finish=True,
                        why=(
                            f"{card.name} is LET GO and not needed in years 2–3. "
                            "Sell after the last year-1 covering."
                            if in_sire
                            else f"{card.name} is LET GO and unused this horizon. Sell this fall."
                        ),
                    )
                )
            continue

        if card.verdict == LET_GO and card.sex == "F":
            if in_dam or covering_dam:
                calendar.append(
                    SaleSlot(
                        animal_id=card.animal_id,
                        name=card.name,
                        sex=card.sex,
                        verdict=card.verdict,
                        window="AFTER_WEANING",
                        path_band=False,
                        path_shrink=True,
                        path_finish=True,
                        why=(
                            f"{card.name} is a year-1 dam"
                            + (" and a covering-cria dam" if covering_dam else "")
                            + ". KEEP DAM BAND keeps the dam band. "
                            "SHRINK sells after the cria is on the ground. "
                            "FINISH THEN SHRINK keeps her for years 2–3, then lists her."
                        ),
                    )
                )
            else:
                calendar.append(
                    SaleSlot(
                        animal_id=card.animal_id,
                        name=card.name,
                        sex=card.sex,
                        verdict=card.verdict,
                        window="THIS_FALL",
                        path_band=True,
                        path_shrink=True,
                        path_finish=True,
                        why=f"{card.name} is LET GO, not a year-1 dam. All sale paths list this fall.",
                    )
                )
            continue

        if card.verdict == KEEP_UNTIL_WEANING:
            if card.sex == "F":
                calendar.append(
                    SaleSlot(
                        animal_id=card.animal_id,
                        name=card.name,
                        sex=card.sex,
                        verdict=card.verdict,
                        window="AFTER_WEANING",
                        path_band=False,
                        path_shrink=True,
                        path_finish=True,
                        why=(
                            f"{card.name} is last-blood today. Covering cria stay. "
                            "KEEP DAM BAND keeps her in the 48. SHRINK lists after weaning. "
                            "FINISH THEN SHRINK keeps her through year 3, then lists her."
                        ),
                    )
                )
            else:
                calendar.append(
                    SaleSlot(
                        animal_id=card.animal_id,
                        name=card.name,
                        sex=card.sex,
                        verdict=card.verdict,
                        window="AFTER_WEANING",
                        path_band=not needed_later,
                        path_shrink=True,
                        path_finish=True,
                        why=(
                            f"{card.name} is last-blood today. Covering cria stay. "
                            + (
                                "Years 2–3 still book them — KEEP DAM BAND holds."
                                if needed_later
                                else "Not needed in years 2–3 — both paths may list after weaning."
                            )
                        ),
                    )
                )
            continue

        calendar.append(
            SaleSlot(
                animal_id=card.animal_id,
                name=card.name,
                sex=card.sex,
                verdict=card.verdict,
                window="HOLD",
                path_band=False,
                path_shrink=False,
                path_finish=False,
                why=f"{card.name} stays on all three paths ({card.verdict}).",
            )
        )
    calendar.sort(key=lambda s: (s.window, s.name))

    cria_cover = [
        (c.cria_id, c.dam_id, c.sire_id, c.name) for c in wean.cover
    ]
    cria_extra = [
        (c.cria_id, c.dam_id, c.sire_id, c.name) for c in extra_cria
    ]

    registered = [rid for rid in herd.registered_ids if rid in herd.animals]

    # Path A: keep every year-1 dam. Sell LET GO sires not needed later
    # (after covering). Keep WAIT. Keep covering cria as carriers.
    # KEEP UNTIL dams stay. KEEP UNTIL sires stay if needed later.
    band_sold = [
        s for s in calendar if s.path_band and s.window != "HOLD"
    ]
    band_sold_ids = {s.animal_id for s in band_sold}
    band_keep = [i for i in registered if i not in band_sold_ids]
    band_banned = {
        s.animal_id for s in calendar if s.sex == "M" and s.path_band and s.window != "HOLD"
    }
    band = _project_herd(
        herd,
        engine,
        band_keep,
        cria_cover + cria_extra,
        pairs,
        capacity,
        band_banned,
        PATH_BAND,
        sorted(s.name for s in band_sold),
    )

    # Path B: sell LET GO + KEEP UNTIL after the windows. Keep WAIT.
    # Keep covering cria + extra last-blood cria. Drop sellable weanlings.
    shrink_sold = [s for s in calendar if s.path_shrink]
    shrink_sold_ids = {s.animal_id for s in shrink_sold}
    shrink_keep = [i for i in registered if i not in shrink_sold_ids]
    shrink_banned = {
        s.animal_id for s in calendar if s.sex == "M" and s.path_shrink
    }
    shrink = _project_herd(
        herd,
        engine,
        shrink_keep,
        cria_cover + cria_extra,
        pairs,
        capacity,
        shrink_banned,
        PATH_SHRINK,
        sorted(s.name for s in shrink_sold),
    )

    core: list[CoreAnimal] = []
    for card in gate.cards:
        if card.verdict != WAIT:
            continue
        core.append(
            CoreAnimal(
                animal_id=card.animal_id,
                name=card.name,
                sex=card.sex,
                mk_pct=card.mk_pct,
                why=card.why,
            )
        )
    core.sort(key=lambda c: (c.sex or "Z", c.name))

    # Path C: run years 1–3 as the printed horizon (same year-2 plan as
    # KEEP DAM BAND), then sell the SHRINK list. Living nucleus after
    # that sale is the shrink nucleus; year-2 bookings stay 48.
    y2_horizon = []
    y2_f_horizon = 0.0
    if len(rotation) > 1:
        y2_horizon = [
            {
                "dam_name": a.dam_name,
                "sire_name": a.sire_name,
                "f_pct": a.f_pct,
                "verdict": a.verdict,
                "reason": a.reason,
            }
            for a in rotation[1].assignments
        ]
        y2_f_horizon = rotation[1].mean_f * 100.0
    finish = Projected(
        path=PATH_FINISH,
        n=shrink.n,
        n_dams=shrink.n_dams,
        n_sires=shrink.n_sires,
        n_unsexed=shrink.n_unsexed,
        n_cria=shrink.n_cria,
        ne=shrink.ne,
        fge=shrink.fge,
        mean_f_pct=shrink.mean_f_pct,
        n_last_founders=shrink.n_last_founders,
        n_irreplaceable=shrink.n_irreplaceable,
        n_year2=len(y2_horizon) or band.n_year2,
        year2_mean_f_pct=y2_f_horizon or band.year2_mean_f_pct,
        year2_unassigned=[],
        year2_plan=y2_horizon or list(band.year2_plan),
        kept=list(shrink.kept),
        sold=list(shrink.sold),
        summary=(
            f"{PATH_FINISH}: years 1–3 keep {band.n_year2} year-2 bookings "
            f"(mean F {y2_f_horizon or band.year2_mean_f_pct:.2f}%). "
            f"After year 3, sell the SHRINK list → {shrink.n} living, "
            f"{shrink.n_dams} dams × {shrink.n_sires} sires, Ne {shrink.ne:.1f}."
        ),
    )

    n_this_fall = sum(1 for s in calendar if s.window == "THIS_FALL")
    n_cover = sum(1 for s in calendar if s.window == "AFTER_COVERING")
    summary = (
        f"{len(collisions)} horizon collisions (LET GO sires still booked in years 2–3). "
        f"{len(core)} pair-locked animals are the residual nucleus. "
        f"{n_this_fall} list this fall on all sale paths. "
        f"{n_cover} sires list after the last covering. "
        f"KEEP DAM BAND → {band.n} living, year-2 bookings {band.n_year2}. "
        f"SHRINK → {shrink.n} living, year-2 bookings {shrink.n_year2}. "
        f"FINISH THEN SHRINK → year-2 bookings {finish.n_year2}, then the shrink sale."
    )
    return NextNucleus(
        collisions=collisions,
        calendar=calendar,
        core=core,
        band=band,
        shrink=shrink,
        finish=finish,
        n_collisions=len(collisions),
        n_core=len(core),
        summary=summary,
    )
