"""Weaning Ledger — which cria must stay if last-carriers leave.

The Gate says a last-carrier may list *after weaning* because a year-1
cria is expected to carry the same founder at ≥ 3.1%. That is only
half the rule. If you sell the parent *and* the cria, the founder is
gone. The ledger is the other half:

  Keep a covering set of cria. Then the KEEP UNTIL WEANING parents
  may leave. Cria that cover no last founder are sellable weanlings.

Cover is greedy set-cover, deterministic: at each step pick the cria
that still covers the most uncovered last-founders, tie-break by name.

Crias are not treated as instant breeders. They only join the living
nucleus as carriers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .gate import (
    KEEP_UNTIL_WEANING,
    LET_GO,
    TheGate,
    _cria_id,
    _cria_name,
    _midparent,
    _shares_of_registered,
)
from .parse import HerdGraph
from .plan import SeasonPlan
from .salvage import MIN_SHARE, _is_real_founder, _name
from .wright import WrightEngine


@dataclass
class CriaStay:
    cria_id: str
    name: str
    dam_id: str
    sire_id: str
    dam_name: str
    sire_name: str
    f_pct: float
    covers: list[str]
    n_covers: int
    must_stay: bool
    sellable: bool
    uniqueness: float
    uniqueness_pct: float
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParentRelease:
    animal_id: str
    name: str
    sex: str | None
    last_of: list[str]
    cria_names: list[str]
    keep_cria: list[str]
    may_sell_after_weaning: bool
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class DisasterRow:
    parent_name: str
    extinct: list[str]
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SaleCard:
    animal_id: str
    name: str
    sex: str | None
    color: str | None
    sire_name: str | None
    dam_name: str | None
    f_pct: float
    mk_pct: float
    ne_delta: float
    hold_for_cria: bool
    cover_cria: list[str]
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class WeaningLedger:
    n_cria: int
    n_cover: int
    n_sellable_cria: int
    n_release: int
    n_uncovered: int
    cover: list[CriaStay]
    stay: list[CriaStay]
    releases: list[ParentRelease]
    uncovered: list[str]
    disaster: list[DisasterRow]
    sale_catalog: list[SaleCard]
    summary: str
    n_hold_for_cria: int = 0
    n_this_fall: int = 0
    threshold: float = MIN_SHARE

    def as_dict(self) -> dict:
        return {
            "n_cria": self.n_cria,
            "n_cover": self.n_cover,
            "n_sellable_cria": self.n_sellable_cria,
            "n_release": self.n_release,
            "n_uncovered": self.n_uncovered,
            "n_hold_for_cria": self.n_hold_for_cria,
            "n_this_fall": self.n_this_fall,
            "threshold": self.threshold,
            "summary": self.summary,
            "cover": [c.as_dict() for c in self.cover],
            "stay": [c.as_dict() for c in self.stay],
            "releases": [r.as_dict() for r in self.releases],
            "uncovered": self.uncovered,
            "disaster": [d.as_dict() for d in self.disaster],
            "sale_catalog": [s.as_dict() for s in self.sale_catalog],
        }


def _greedy_cover(cria_sets: dict[str, set[str]], universe: set[str], names: dict[str, str]) -> list[str]:
    remaining = set(universe)
    chosen: list[str] = []
    unused = {k: set(v) for k, v in cria_sets.items()}
    while remaining:
        best = None
        best_gain = 0
        best_name = ""
        for cid, covers in unused.items():
            gain = len(covers & remaining)
            nm = names.get(cid, cid)
            if gain > best_gain or (gain == best_gain and best is not None and nm < best_name):
                if gain > 0:
                    best = cid
                    best_gain = gain
                    best_name = nm
        if best is None:
            break
        chosen.append(best)
        remaining -= unused[best]
        del unused[best]
    return chosen


def weaning_ledger(
    herd: HerdGraph,
    engine: WrightEngine,
    plan: SeasonPlan | None,
    gate: TheGate,
    min_share: float = MIN_SHARE,
) -> WeaningLedger:
    registered, shares = _shares_of_registered(herd)
    assignments = list(plan.assignments) if plan else []
    by_id = {c.animal_id: c for c in gate.cards}

    cria_shares: dict[str, dict[str, float]] = {}
    cria_meta: dict[str, tuple] = {}
    for a in assignments:
        cid = _cria_id(a.year, a.dam_id, a.sire_id)
        cria_shares[cid] = _midparent(shares.get(a.dam_id, {}), shares.get(a.sire_id, {}))
        cria_meta[cid] = (a.dam_id, a.sire_id, a.dam_name, a.sire_name, a.f_pct)

    last_founders: dict[str, str] = {}
    parent_of_founder: dict[str, str] = {}
    for c in gate.cards:
        if not c.last_of_now:
            continue
        smap = shares.get(c.animal_id, {})
        for fid, val in smap.items():
            if not _is_real_founder(fid) or val < min_share:
                continue
            fname = _name(herd, fid)
            if fname in c.last_of_now:
                last_founders[fid] = fname
                parent_of_founder[fid] = c.animal_id

    universe = set(last_founders)
    cria_sets: dict[str, set[str]] = {}
    cria_uniqueness: dict[str, float] = {}
    for cid, smap in cria_shares.items():
        covered: set[str] = set()
        uniq = 0.0
        for fid, val in smap.items():
            if fid in universe and val >= min_share:
                covered.add(fid)
                uniq += val
        cria_sets[cid] = covered
        cria_uniqueness[cid] = uniq

    names = {cid: _cria_name(meta[2], meta[3]) for cid, meta in cria_meta.items()}
    cover_ids = _greedy_cover(cria_sets, universe, names)
    cover_set = set(cover_ids)
    covered_founders: set[str] = set()
    for cid in cover_ids:
        covered_founders |= cria_sets[cid]
    uncovered = sorted(last_founders[f] for f in universe - covered_founders)

    stay: list[CriaStay] = []
    for cid, meta in cria_meta.items():
        dam_id, sire_id, dam_name, sire_name, f_pct = meta
        covers_names = sorted(last_founders[f] for f in cria_sets[cid])
        must = cid in cover_set
        sellable = not covers_names
        uniq = cria_uniqueness[cid]
        if must:
            why = (
                f"Must stay. Covers {len(covers_names)} last founder(s) "
                f"the year-1 parents would take with them: "
                f"{', '.join(covers_names[:3])}"
                f"{' (+'+str(len(covers_names)-3)+' more)' if len(covers_names)>3 else ''}."
            )
        elif covers_names:
            why = (
                f"Also carries {', '.join(covers_names[:3])} "
                "but a leaner cria already covers that blood. Sellable if the cover stays."
            )
        else:
            why = "Carries no last founder at ≥ 3.1%. Sellable weanling."
        stay.append(
            CriaStay(
                cria_id=cid,
                name=names[cid],
                dam_id=dam_id,
                sire_id=sire_id,
                dam_name=dam_name,
                sire_name=sire_name,
                f_pct=f_pct,
                covers=covers_names,
                n_covers=len(covers_names),
                must_stay=must,
                sellable=sellable,
                uniqueness=uniq,
                uniqueness_pct=round(uniq * 100.0, 2),
                why=why,
            )
        )
    stay.sort(key=lambda c: (-c.must_stay, -c.n_covers, -c.uniqueness, c.name))
    cover = [c for c in stay if c.must_stay]

    cria_by_parent: dict[str, list[CriaStay]] = {}
    for c in stay:
        cria_by_parent.setdefault(c.dam_id, []).append(c)
        cria_by_parent.setdefault(c.sire_id, []).append(c)

    releases: list[ParentRelease] = []
    for card in gate.cards:
        if card.verdict != KEEP_UNTIL_WEANING:
            continue
        kids = cria_by_parent.get(card.animal_id, [])
        keep = [k.name for k in kids if k.must_stay]
        kid_names = [k.name for k in kids]
        may = bool(keep) or (not card.last_of_now)
        if keep:
            why = (
                f"After weaning, {card.name} may leave if the barn keeps "
                f"{', '.join(keep[:3])}"
                f"{' (+'+str(len(keep)-3)+' more)' if len(keep)>3 else ''}."
            )
        elif kid_names:
            why = (
                f"{card.name} is duplicated by {', '.join(kid_names[:2])}, "
                "but the covering set picked a different cria for that blood."
            )
            may = True
        else:
            why = f"{card.name} has no year-1 cria. Cannot release."
            may = False
        releases.append(
            ParentRelease(
                animal_id=card.animal_id,
                name=card.name,
                sex=card.sex,
                last_of=list(card.last_of_now),
                cria_names=kid_names,
                keep_cria=keep,
                may_sell_after_weaning=may,
                why=why,
            )
        )
    releases.sort(key=lambda r: (-len(r.last_of), r.name))

    disaster: list[DisasterRow] = []
    for card in gate.cards:
        if card.verdict != KEEP_UNTIL_WEANING:
            continue
        kids = cria_by_parent.get(card.animal_id, [])
        kid_ids = {k.cria_id for k in kids}
        remaining_carriers = {rid for rid in registered if rid != card.animal_id}
        extinct: list[str] = []
        for fid, fname in last_founders.items():
            if parent_of_founder.get(fid) != card.animal_id:
                continue
            still = False
            for oid in remaining_carriers:
                if shares.get(oid, {}).get(fid, 0.0) >= min_share:
                    still = True
                    break
            if not still:
                for cid, smap in cria_shares.items():
                    if cid in kid_ids:
                        continue
                    if smap.get(fid, 0.0) >= min_share:
                        still = True
                        break
            if not still:
                extinct.append(fname)
        if extinct:
            disaster.append(
                DisasterRow(
                    parent_name=card.name,
                    extinct=extinct,
                    why=(
                        f"Selling {card.name} and every cria of that pairing "
                        f"takes {', '.join(extinct[:3])}"
                        f"{' (+'+str(len(extinct)-3)+' more)' if len(extinct)>3 else ''} "
                        "out of the nucleus."
                    ),
                )
            )
    disaster.sort(key=lambda d: (-len(d.extinct), d.parent_name))

    catalog: list[SaleCard] = []
    leave_by_id = {x.animal_id: x for x in gate.leave}
    cover_by_parent: dict[str, list[str]] = {}
    for c in cover:
        cover_by_parent.setdefault(c.dam_id, []).append(c.name)
        cover_by_parent.setdefault(c.sire_id, []).append(c.name)
    for card in gate.cards:
        if card.verdict != LET_GO:
            continue
        node = herd.animals.get(card.animal_id)
        leave = leave_by_id.get(card.animal_id)
        carrying = cover_by_parent.get(card.animal_id, [])
        if carrying:
            why = (
                f"{card.name} is LET GO genetically, but is a parent of a covering cria "
                f"({', '.join(carrying[:2])}). Wait until that cria is on the ground."
            )
        else:
            why = card.why
        catalog.append(
            SaleCard(
                animal_id=card.animal_id,
                name=card.name,
                sex=card.sex,
                color=node.color if node else None,
                sire_name=_name(herd, node.sire_key) if node and node.sire_key else None,
                dam_name=_name(herd, node.dam_key) if node and node.dam_key else None,
                f_pct=round(engine.f(card.animal_id) * 100.0, 2),
                mk_pct=card.mk_pct,
                ne_delta=leave.ne_delta if leave else card.ne_delta_if_sold,
                hold_for_cria=bool(carrying),
                cover_cria=carrying,
                why=why,
            )
        )
    catalog.sort(key=lambda s: (s.hold_for_cria, -s.mk_pct, s.name))

    n_release = sum(1 for r in releases if r.may_sell_after_weaning)
    n_sellable = sum(1 for c in stay if c.sellable)
    n_hold = sum(1 for s in catalog if s.hold_for_cria)
    n_fall = len(catalog) - n_hold
    summary = (
        f"Keep {len(cover)} of {len(stay)} year-1 cria and {n_release} last-carriers "
        f"may leave after weaning. {n_sellable} cria cover no last founder — "
        f"sellable weanlings. {n_fall} LET GO can list this fall; "
        f"{n_hold} LET GO wait because they are parents of a covering cria. "
        f"{len(uncovered)} last founders have no cria backup."
    )
    return WeaningLedger(
        n_cria=len(stay),
        n_cover=len(cover),
        n_sellable_cria=n_sellable,
        n_release=n_release,
        n_uncovered=len(uncovered),
        cover=cover,
        stay=stay,
        releases=releases,
        uncovered=uncovered,
        disaster=disaster,
        sale_catalog=catalog,
        n_hold_for_cria=n_hold,
        n_this_fall=n_fall,
        summary=summary,
        threshold=min_share,
    )
