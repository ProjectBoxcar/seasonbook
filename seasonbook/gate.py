"""The Gate — Keep / Let Go on the living nucleus.

Last Blood answers *who is irreplaceable*. The farm's next question is
the sale list: who can leave this fall, who cannot be sold as a pair,
and what the year-1 cria crop actually duplicates.

Science is the same Mendelian walk as the census. A registered animal
is a carrier of a founder when expected share ≥ 1/32. Cria founder
share is the mid-parent value (½ dam + ½ sire). Kinship of the cria
crop is Malécot: θ(cria, X) = ½(θ(sire, X) + θ(dam, X)). Crias are
not treated as instant breeders — they only join the living nucleus.

Verdicts:

  KEEP                last carrier of a founder the year-1 cria will
                      not duplicate (share falls below 3.1%, or the
                      animal is not booked).
  KEEP_UNTIL_WEANING  last now; at least one booked cria is expected
                      to carry the same founder at ≥ 3.1%.
  WAIT                one of two living carriers. Selling both kills
                      the founder. Selling one makes the other last.
  LET_GO              not a 1- or 2-carrier of anything at threshold.
                      Highest mean-kinship first — those are the
                      animals whose exit *helps* Ne.

UNK-* slots are missing-parent placeholders, not real founders.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from .census import expected_founder_contributions
from .parse import HerdGraph
from .plan import SeasonPlan
from .salvage import MIN_SHARE, _is_real_founder, _name
from .wright import WrightEngine

KEEP = "KEEP"
KEEP_UNTIL_WEANING = "KEEP_UNTIL_WEANING"
WAIT = "WAIT"
LET_GO = "LET_GO"

VERDICT_ORDER = {
    KEEP: 0,
    KEEP_UNTIL_WEANING: 1,
    WAIT: 2,
    LET_GO: 3,
}


def _finite(x: float) -> float:
    if x != x or x in (float("inf"), float("-inf")):
        return 0.0
    return float(x)


def _ne_fge(matrix: list[list[float]]) -> tuple[float, float, float, float]:
    """mean pairwise MK, mean including diagonal, fge, Ne."""
    n = len(matrix)
    if n < 2:
        return 0.0, 0.0, 0.0, 0.0
    off: list[float] = []
    incl: list[float] = []
    for i in range(n):
        for j in range(n):
            incl.append(matrix[i][j])
            if i < j:
                off.append(matrix[i][j])
    mean_mk = sum(off) / len(off) if off else 0.0
    mean_incl = sum(incl) / len(incl) if incl else 0.0
    fge = (1.0 / (2.0 * mean_incl)) if mean_incl > 0 else 0.0
    ne = (1.0 / (2.0 * mean_mk)) if mean_mk > 0 else 0.0
    return mean_mk, mean_incl, fge, ne


def _without_index(matrix: list[list[float]], drop: int) -> list[list[float]]:
    return [
        [row[j] for j in range(len(row)) if j != drop]
        for i, row in enumerate(matrix)
        if i != drop
    ]


def _without_indices(matrix: list[list[float]], drops: set[int]) -> list[list[float]]:
    keep = [i for i in range(len(matrix)) if i not in drops]
    return [[matrix[i][j] for j in keep] for i in keep]


@dataclass
class LeaveImpact:
    animal_id: str
    name: str
    sex: str | None
    mk: float
    mk_pct: float
    extinct_founders: list[str]
    new_last: list[dict]
    new_rare: list[dict]
    ne_before: float
    ne_after: float
    ne_delta: float
    fge_before: float
    fge_after: float
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PairLock:
    founder_id: str
    founder_name: str
    a_id: str
    a_name: str
    b_id: str
    b_name: str
    a_share_pct: float
    b_share_pct: float
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class GateCard:
    animal_id: str
    name: str
    sex: str | None
    mk: float
    mk_pct: float
    uniqueness: float
    uniqueness_pct: float
    in_year1_plan: bool
    booked_as: str
    verdict: str
    last_of_now: list[str]
    last_of_after: list[str]
    rare_of_now: list[str]
    duplicated_by_cria: list[str]
    extinct_if_sold: list[str]
    ne_delta_if_sold: float
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RescuedFounder:
    founder_id: str
    founder_name: str
    carrier_now: str
    n_carriers_after: int
    cria_names: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class AfterCria:
    n_cria: int
    n_nucleus: int
    n_irreplaceable_now: int
    n_irreplaceable_after: int
    n_last_founders_now: int
    n_last_founders_after: int
    n_rare_now: int
    n_rare_after: int
    mean_mk_now: float
    mean_mk_after: float
    ne_now: float
    ne_after: float
    fge_now: float
    fge_after: float
    rescued_founders: list[RescuedFounder]
    still_last: list[dict]
    summary: str

    def as_dict(self) -> dict:
        return {
            "n_cria": self.n_cria,
            "n_nucleus": self.n_nucleus,
            "n_irreplaceable_now": self.n_irreplaceable_now,
            "n_irreplaceable_after": self.n_irreplaceable_after,
            "n_last_founders_now": self.n_last_founders_now,
            "n_last_founders_after": self.n_last_founders_after,
            "n_rare_now": self.n_rare_now,
            "n_rare_after": self.n_rare_after,
            "mean_mk_now": round(self.mean_mk_now * 100.0, 4),
            "mean_mk_after": round(self.mean_mk_after * 100.0, 4),
            "ne_now": round(self.ne_now, 1),
            "ne_after": round(self.ne_after, 1),
            "fge_now": round(self.fge_now, 2),
            "fge_after": round(self.fge_after, 2),
            "rescued_founders": [r.as_dict() for r in self.rescued_founders],
            "still_last": self.still_last,
            "summary": self.summary,
        }


@dataclass
class SuggestedSale:
    n: int
    names: list[str]
    ids: list[str]
    ne_before: float
    ne_after: float
    ne_delta: float
    fge_before: float
    fge_after: float
    extinct: list[str]
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class TheGate:
    cards: list[GateCard]
    leave: list[LeaveImpact]
    pair_locks: list[PairLock]
    after: AfterCria
    suggested_sale: SuggestedSale
    n_keep: int = 0
    n_keep_until: int = 0
    n_wait: int = 0
    n_let_go: int = 0
    threshold: float = MIN_SHARE
    summary: str = ""

    def as_dict(self) -> dict:
        return {
            "n_keep": self.n_keep,
            "n_keep_until": self.n_keep_until,
            "n_wait": self.n_wait,
            "n_let_go": self.n_let_go,
            "threshold": self.threshold,
            "summary": self.summary,
            "cards": [c.as_dict() for c in self.cards],
            "leave": [x.as_dict() for x in self.leave],
            "pair_locks": [p.as_dict() for p in self.pair_locks],
            "after": self.after.as_dict(),
            "suggested_sale": self.suggested_sale.as_dict(),
        }


def _shares_of_registered(herd: HerdGraph) -> tuple[list[str], dict[str, dict[str, float]]]:
    registered = [rid for rid in herd.registered_ids if rid in herd.animals]
    shares = {rid: expected_founder_contributions(rid, herd) for rid in registered}
    return registered, shares


def _carrier_index(
    shares: dict[str, dict[str, float]],
    min_share: float,
) -> dict[str, list[tuple[str, float]]]:
    carriers: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for rid, smap in shares.items():
        for fid, val in smap.items():
            if _is_real_founder(fid) and val >= min_share:
                carriers[fid].append((rid, val))
    for fid in carriers:
        carriers[fid].sort(key=lambda kv: -kv[1])
    return carriers


def _cria_id(year: int, dam_id: str, sire_id: str) -> str:
    return f"CRIA:{year}:{dam_id}:{sire_id}"


def _cria_name(dam_name: str, sire_name: str) -> str:
    return f"{dam_name} × {sire_name}"


def _midparent(dam: dict[str, float], sire: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for k in set(dam) | set(sire):
        out[k] = 0.5 * dam.get(k, 0.0) + 0.5 * sire.get(k, 0.0)
    return out


def _extend_kinship(
    matrix: list[list[float]],
    ids: list[str],
    assignments: list,
) -> tuple[list[list[float]], list[str]]:
    """Append one row/col per year-1 cria using parent coancestry.

    θ(cria, X) = ½(θ(sire, X) + θ(dam, X))
    θ(cria, cria) = (1 + θ(sire, dam)) / 2
    θ(c1, c2) = ¼(θ(s1,s2) + θ(s1,d2) + θ(d1,s2) + θ(d1,d2))
    """
    idx = {aid: i for i, aid in enumerate(ids)}
    n = len(ids)
    cria_ids = [_cria_id(a.year, a.dam_id, a.sire_id) for a in assignments]
    m = n + len(assignments)
    out = [[0.0] * m for _ in range(m)]
    for i in range(n):
        for j in range(n):
            out[i][j] = matrix[i][j]

    def theta(a: str, b: str) -> float:
        if a not in idx or b not in idx:
            return 0.0
        return matrix[idx[a]][idx[b]]

    for k, a in enumerate(assignments):
        ci = n + k
        # cria × living nucleus
        for j, rid in enumerate(ids):
            t = 0.5 * (theta(a.sire_id, rid) + theta(a.dam_id, rid))
            out[ci][j] = t
            out[j][ci] = t
        # cria self
        f_cria = theta(a.sire_id, a.dam_id)
        out[ci][ci] = (1.0 + f_cria) / 2.0

    for k1, a1 in enumerate(assignments):
        for k2 in range(k1 + 1, len(assignments)):
            a2 = assignments[k2]
            t = 0.25 * (
                theta(a1.sire_id, a2.sire_id)
                + theta(a1.sire_id, a2.dam_id)
                + theta(a1.dam_id, a2.sire_id)
                + theta(a1.dam_id, a2.dam_id)
            )
            i, j = n + k1, n + k2
            out[i][j] = t
            out[j][i] = t

    return out, ids + cria_ids


def _leave_why(
    name: str,
    extinct: list[str],
    new_last: list[dict],
    ne_delta: float,
) -> str:
    if extinct:
        lost = ", ".join(extinct[:3])
        extra = f" (+{len(extinct) - 3} more)" if len(extinct) > 3 else ""
        return f"Selling {name} takes {lost}{extra} out of the nucleus."
    if new_last:
        row = new_last[0]
        return (
            f"Selling {name} makes {row['remaining_name']} the last living "
            f"carrier of {row['founder_name']}."
        )
    sign = "raises" if ne_delta > 0 else "lowers"
    return f"Selling {name} {sign} Ne by {abs(ne_delta):.1f}."


def _verdict_why(
    name: str,
    verdict: str,
    last_now: list[str],
    last_after: list[str],
    duplicated: list[str],
    rare: list[str],
    booked: bool,
) -> str:
    if verdict == KEEP:
        carried = ", ".join(last_after[:3]) or ", ".join(last_now[:3])
        extra = ""
        src = last_after or last_now
        if len(src) > 3:
            extra = f" (+{len(src) - 3} more)"
        if not booked:
            return (
                f"{name} is the last living carrier of {carried}{extra} "
                "and is not booked — the cria crop cannot duplicate this blood."
            )
        return (
            f"{name} is booked, but the cria's expected share of "
            f"{carried}{extra} still falls below 3.1%. Keep."
        )
    if verdict == KEEP_UNTIL_WEANING:
        carried = ", ".join(duplicated[:3])
        extra = f" (+{len(duplicated) - 3} more)" if len(duplicated) > 3 else ""
        return (
            f"{name} is the last living carrier of {carried}{extra} today. "
            "A year-1 cria is expected to carry it at ≥ 3.1% — keep until weaning."
        )
    if verdict == WAIT:
        carried = ", ".join(rare[:3])
        extra = f" (+{len(rare) - 3} more)" if len(rare) > 3 else ""
        return (
            f"{name} is one of two living carriers of {carried}{extra}. "
            "Do not sell both."
        )
    return (
        f"{name} is not a last or pair-locked carrier at the 3.1% threshold. "
        "Highest MK animals on this list are the ones whose exit helps Ne."
    )


def _suggested_sale(
    cards: list[GateCard],
    pair_locks: list[PairLock],
    matrix: list[list[float]],
    ids: list[str],
    ne_now: float,
    fge_now: float,
    n: int = 5,
) -> SuggestedSale:
    locked = set()
    for p in pair_locks:
        locked.add(p.a_id)
        locked.add(p.b_id)
    pool = [c for c in cards if c.verdict == LET_GO]
    pool.sort(key=lambda c: (-c.mk, c.name))
    pick = pool[:n]
    pick_ids = {c.animal_id for c in pick}
    idx = {aid: i for i, aid in enumerate(ids)}
    drops = {idx[i] for i in pick_ids if i in idx}
    after = _without_indices(matrix, drops) if drops else matrix
    _, _, fge_after, ne_after = _ne_fge(after)
    names = [c.name for c in pick]
    why = (
        f"Top {len(pick)} LET GO by mean kinship. None is last or pair-locked. "
        f"Ne {ne_now:.1f} → {ne_after:.1f}."
        if pick
        else "No LET GO animals at this threshold."
    )
    return SuggestedSale(
        n=len(pick),
        names=names,
        ids=[c.animal_id for c in pick],
        ne_before=round(ne_now, 1),
        ne_after=round(ne_after, 1),
        ne_delta=round(ne_after - ne_now, 1),
        fge_before=round(fge_now, 2),
        fge_after=round(fge_after, 2),
        extinct=[],
        why=why,
    )


def the_gate(
    herd: HerdGraph,
    engine: WrightEngine,
    plan: SeasonPlan | None = None,
    min_share: float = MIN_SHARE,
) -> TheGate:
    registered, shares = _shares_of_registered(herd)
    carriers_now = _carrier_index(shares, min_share)
    matrix = engine.kinship_matrix(registered)
    mean_mk, _, fge_now, ne_now = _ne_fge(matrix)
    idx = {aid: i for i, aid in enumerate(registered)}

    booked_dam: set[str] = set()
    booked_sire: set[str] = set()
    assignments = list(plan.assignments) if plan else []
    for a in assignments:
        booked_dam.add(a.dam_id)
        booked_sire.add(a.sire_id)
    booked = booked_dam | booked_sire

    # Cria mid-parent shares
    cria_shares: dict[str, dict[str, float]] = {}
    cria_meta: dict[str, tuple[str, str, str]] = {}
    for a in assignments:
        cid = _cria_id(a.year, a.dam_id, a.sire_id)
        cria_shares[cid] = _midparent(
            shares.get(a.dam_id, {}),
            shares.get(a.sire_id, {}),
        )
        cria_meta[cid] = (a.dam_name, a.sire_name, _cria_name(a.dam_name, a.sire_name))

    shares_after = dict(shares)
    shares_after.update(cria_shares)
    carriers_after = _carrier_index(shares_after, min_share)

    last_of_now: dict[str, list[str]] = {rid: [] for rid in registered}
    rare_of_now: dict[str, list[str]] = {rid: [] for rid in registered}
    uniqueness: dict[str, float] = {rid: 0.0 for rid in registered}
    last_founders_now: list[str] = []
    rare_founders_now: list[str] = []
    for fid, car in carriers_now.items():
        fname = _name(herd, fid)
        if len(car) == 1:
            last_founders_now.append(fid)
            last_of_now[car[0][0]].append(fname)
            rare_of_now[car[0][0]].append(fname)
            uniqueness[car[0][0]] += car[0][1]
        elif len(car) == 2:
            rare_founders_now.append(fid)
            for rid, val in car:
                rare_of_now[rid].append(fname)
                uniqueness[rid] += val

    last_of_after: dict[str, list[str]] = {rid: [] for rid in registered}
    duplicated: dict[str, list[str]] = {rid: [] for rid in registered}
    rescued: list[RescuedFounder] = []
    still_last: list[dict] = []
    last_founders_after: list[str] = []
    rare_after_ids: list[str] = []

    for fid, car_after in carriers_after.items():
        fname = _name(herd, fid)
        n_after = len(car_after)
        if n_after == 1:
            last_founders_after.append(fid)
            only_id, only_share = car_after[0]
            if only_id in last_of_after:
                last_of_after[only_id].append(fname)
            still_last.append(
                {
                    "founder_id": fid,
                    "founder_name": fname,
                    "carrier_id": only_id,
                    "carrier_name": (
                        herd.animals[only_id].name
                        if only_id in herd.animals
                        else cria_meta.get(only_id, ("", "", only_id))[2]
                    ),
                    "share_pct": round(only_share * 100.0, 2),
                    "is_cria": only_id.startswith("CRIA:"),
                }
            )
        if 1 <= n_after <= 2:
            rare_after_ids.append(fid)
        car_now = carriers_now.get(fid, [])
        if len(car_now) == 1 and n_after >= 2:
            cria_hits = [
                cria_meta[cid][2]
                for cid, _ in car_after
                if cid.startswith("CRIA:") and cid in cria_meta
            ]
            rescued.append(
                RescuedFounder(
                    founder_id=fid,
                    founder_name=fname,
                    carrier_now=_name(herd, car_now[0][0]),
                    n_carriers_after=n_after,
                    cria_names=cria_hits,
                )
            )
            orig = car_now[0][0]
            if orig in duplicated:
                duplicated[orig].append(fname)

    rescued.sort(key=lambda r: r.founder_name)
    still_last.sort(key=lambda r: r["founder_name"])

    # Pair locks: exactly two living carriers today
    pair_locks: list[PairLock] = []
    for fid in rare_founders_now:
        car = carriers_now[fid]
        if len(car) != 2:
            continue
        (a_id, a_s), (b_id, b_s) = car[0], car[1]
        fname = _name(herd, fid)
        a_name = _name(herd, a_id)
        b_name = _name(herd, b_id)
        pair_locks.append(
            PairLock(
                founder_id=fid,
                founder_name=fname,
                a_id=a_id,
                a_name=a_name,
                b_id=b_id,
                b_name=b_name,
                a_share_pct=round(a_s * 100.0, 2),
                b_share_pct=round(b_s * 100.0, 2),
                why=(
                    f"Do not sell {a_name} and {b_name} together — "
                    f"they are the only two living carriers of {fname}."
                ),
            )
        )
    pair_locks.sort(key=lambda p: p.founder_name)

    # If they leave
    leave: list[LeaveImpact] = []
    leave_by_id: dict[str, LeaveImpact] = {}
    for rid in registered:
        node = herd.animals[rid]
        extinct: list[str] = []
        new_last: list[dict] = []
        new_rare: list[dict] = []
        for fid, car in carriers_now.items():
            ids_here = [c[0] for c in car]
            if rid not in ids_here:
                continue
            remaining = [(c, s) for c, s in car if c != rid]
            fname = _name(herd, fid)
            if not remaining:
                extinct.append(fname)
            elif len(car) == 2 and len(remaining) == 1:
                other_id, other_s = remaining[0]
                new_last.append(
                    {
                        "founder_id": fid,
                        "founder_name": fname,
                        "remaining_id": other_id,
                        "remaining_name": _name(herd, other_id),
                        "remaining_share_pct": round(other_s * 100.0, 2),
                    }
                )
            elif len(car) == 3 and len(remaining) == 2:
                new_rare.append(
                    {
                        "founder_id": fid,
                        "founder_name": fname,
                        "remaining": [_name(herd, c) for c, _ in remaining],
                    }
                )
        drop_i = idx[rid]
        _, _, fge_a, ne_a = _ne_fge(_without_index(matrix, drop_i))
        mk = engine.mean_kinship(rid, registered)
        impact = LeaveImpact(
            animal_id=rid,
            name=node.name,
            sex=node.sex,
            mk=mk,
            mk_pct=round(mk * 100.0, 2),
            extinct_founders=extinct,
            new_last=new_last,
            new_rare=new_rare,
            ne_before=round(ne_now, 1),
            ne_after=round(ne_a, 1),
            ne_delta=round(ne_a - ne_now, 1),
            fge_before=round(fge_now, 2),
            fge_after=round(fge_a, 2),
            why=_leave_why(node.name, extinct, new_last, ne_a - ne_now),
        )
        leave.append(impact)
        leave_by_id[rid] = impact
    leave.sort(key=lambda x: (-len(x.extinct_founders), -x.mk, x.name))

    # Cards + verdicts
    cards: list[GateCard] = []
    for rid in registered:
        node = herd.animals[rid]
        last_now = last_of_now[rid]
        last_aft = last_of_after[rid]
        rare = rare_of_now[rid]
        dup = duplicated[rid]
        mk = engine.mean_kinship(rid, registered)
        in_plan = rid in booked
        if rid in booked_dam and rid in booked_sire:
            booked_as = "both"
        elif rid in booked_dam:
            booked_as = "dam"
        elif rid in booked_sire:
            booked_as = "sire"
        else:
            booked_as = ""
        if last_now and last_aft:
            verdict = KEEP
        elif last_now:
            verdict = KEEP_UNTIL_WEANING
        elif rare:
            verdict = WAIT
        else:
            verdict = LET_GO
        impact = leave_by_id[rid]
        cards.append(
            GateCard(
                animal_id=rid,
                name=node.name,
                sex=node.sex,
                mk=mk,
                mk_pct=round(mk * 100.0, 2),
                uniqueness=uniqueness[rid],
                uniqueness_pct=round(uniqueness[rid] * 100.0, 2),
                in_year1_plan=in_plan,
                booked_as=booked_as,
                verdict=verdict,
                last_of_now=last_now,
                last_of_after=last_aft,
                rare_of_now=rare,
                duplicated_by_cria=dup,
                extinct_if_sold=impact.extinct_founders,
                ne_delta_if_sold=impact.ne_delta,
                why=_verdict_why(node.name, verdict, last_now, last_aft, dup, rare, in_plan),
            )
        )
    cards.sort(key=lambda c: (VERDICT_ORDER[c.verdict], -c.uniqueness, -c.mk, c.name))

    # After-cria kinship
    if assignments:
        matrix_after, _ = _extend_kinship(matrix, registered, assignments)
        mean_mk_after, _, fge_after, ne_after = _ne_fge(matrix_after)
    else:
        mean_mk_after, fge_after, ne_after = mean_mk, fge_now, ne_now

    irrep_now = sum(1 for c in cards if c.last_of_now)
    irrep_after = len({row["carrier_id"] for row in still_last})

    after = AfterCria(
        n_cria=len(assignments),
        n_nucleus=len(registered) + len(assignments),
        n_irreplaceable_now=irrep_now,
        n_irreplaceable_after=irrep_after,
        n_last_founders_now=len(last_founders_now),
        n_last_founders_after=len(last_founders_after),
        n_rare_now=len(last_founders_now) + len(rare_founders_now),
        n_rare_after=len(rare_after_ids),
        mean_mk_now=mean_mk,
        mean_mk_after=mean_mk_after,
        ne_now=_finite(ne_now),
        ne_after=_finite(ne_after),
        fge_now=_finite(fge_now),
        fge_after=_finite(fge_after),
        rescued_founders=rescued,
        still_last=still_last,
        summary=(
            f"After {len(assignments)} year-1 cria hit the ground: "
            f"last founders {len(last_founders_now)} → {len(last_founders_after)}, "
            f"irreplaceable animals {irrep_now} → {irrep_after}, "
            f"Ne {ne_now:.1f} → {ne_after:.1f}. "
            f"{len(rescued)} last founders get a second carrier from the cria crop."
        ),
    )

    n_keep = sum(1 for c in cards if c.verdict == KEEP)
    n_keep_until = sum(1 for c in cards if c.verdict == KEEP_UNTIL_WEANING)
    n_wait = sum(1 for c in cards if c.verdict == WAIT)
    n_let_go = sum(1 for c in cards if c.verdict == LET_GO)

    sale = _suggested_sale(cards, pair_locks, matrix, registered, ne_now, fge_now, n=5)

    summary = (
        f"{n_keep} KEEP  ·  {n_keep_until} KEEP UNTIL WEANING  ·  "
        f"{n_wait} WAIT  ·  {n_let_go} LET GO. "
        f"{len(pair_locks)} pair-locks (do not sell both). "
        f"{after.summary}"
    )
    return TheGate(
        cards=cards,
        leave=leave,
        pair_locks=pair_locks,
        after=after,
        suggested_sale=sale,
        n_keep=n_keep,
        n_keep_until=n_keep_until,
        n_wait=n_wait,
        n_let_go=n_let_go,
        threshold=min_share,
        summary=summary,
    )


def explain_leave(gate: TheGate, name: str) -> LeaveImpact | None:
    needle = name.strip().upper()
    for row in gate.leave:
        if row.name.upper() == needle or needle in row.name.upper():
            return row
    return None
