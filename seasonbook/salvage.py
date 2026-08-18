"""Last Blood — founders that vanish if a living animal is not bred.

Expected founder contribution is the Mendelian 50/50 walk already used
by the census. A founder is *rare* when at most two registered animals
carry a real share of it (≥ 1/32). It is *last* when only one does.

An animal is irreplaceable when it is the only living carrier of at
least one founder. Uniqueness is the sum of those rare-founder shares:
the fraction of that animal that the rest of the nucleus does not have.

UNK-* slots are missing-parent placeholders, not real founders.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .census import expected_founder_contributions
from .parse import HerdGraph
from .plan import Assignment, Pair, SeasonPlan, _bench
from .wright import WrightEngine

# Dust below first-cousin-once-removed equivalent is ignored.
MIN_SHARE = 1.0 / 32.0
RARE_CARRIER_MAX = 2


@dataclass
class Carrier:
    animal_id: str
    name: str
    sex: str | None
    share: float
    share_pct: float


@dataclass
class FounderRisk:
    founder_id: str
    founder_name: str
    n_carriers: int
    last: bool
    carriers: list[Carrier]
    herd_share: float


@dataclass
class SalvageCard:
    animal_id: str
    name: str
    sex: str | None
    mk: float
    mk_pct: float
    uniqueness: float
    uniqueness_pct: float
    last_of: list[str]
    rare_of: list[str]
    in_year1_plan: bool
    irreplaceable: bool
    why: str


@dataclass
class LastBlood:
    rare_founders: list[FounderRisk]
    last_founders: list[FounderRisk]
    cards: list[SalvageCard]
    sitting_out: list[SalvageCard]
    rescue: list[dict] = field(default_factory=list)
    n_irreplaceable: int = 0
    n_rare_founders: int = 0
    n_last_founders: int = 0
    threshold: float = MIN_SHARE

    def as_dict(self) -> dict:
        return {
            "n_irreplaceable": self.n_irreplaceable,
            "n_rare_founders": self.n_rare_founders,
            "n_last_founders": self.n_last_founders,
            "threshold": self.threshold,
            "rare_founders": [_founder_d(f) for f in self.rare_founders],
            "last_founders": [_founder_d(f) for f in self.last_founders],
            "cards": [asdict(c) for c in self.cards],
            "sitting_out": [asdict(c) for c in self.sitting_out],
            "rescue": self.rescue,
        }


def _founder_d(f: FounderRisk) -> dict:
    return {
        "founder_id": f.founder_id,
        "founder_name": f.founder_name,
        "n_carriers": f.n_carriers,
        "last": f.last,
        "herd_share": f.herd_share,
        "carriers": [asdict(c) for c in f.carriers],
    }


def _is_real_founder(fid: str) -> bool:
    return not fid.startswith("UNK-")


def _name(herd: HerdGraph, ident: str) -> str:
    node = herd.animals.get(ident)
    if node and node.name:
        return node.name
    return ident


def rescue_bookings(
    sitting: list[SalvageCard],
    pairs: list[Pair] | None,
) -> list[dict]:
    """One legal, lowest-F dam for each last-carrier sire sitting on the bench."""
    if not pairs:
        return []
    out: list[dict] = []
    for card in sitting:
        if card.sex != "M":
            continue
        legal = [p for p in pairs if p.sire_id == card.animal_id and p.verdict != "BLOCK"]
        if not legal:
            continue
        pick = min(legal, key=lambda p: (p.F, p.dam_name))
        carried = ", ".join(card.last_of[:3])
        extra = f" (+{len(card.last_of) - 3} more)" if len(card.last_of) > 3 else ""
        out.append(
            {
                "sire_id": card.animal_id,
                "sire_name": card.name,
                "dam_id": pick.dam_id,
                "dam_name": pick.dam_name,
                "f_pct": pick.f_pct,
                "uniqueness_pct": card.uniqueness_pct,
                "last_of": list(card.last_of),
                "why": (
                    f"One booking of {card.name} × {pick.dam_name} "
                    f"(F={pick.f_pct:.2f}%) keeps {carried}{extra}."
                ),
            }
        )
    return out


def apply_rescue(
    plan: SeasonPlan,
    pairs: list[Pair],
    herd: HerdGraph,
    engine: WrightEngine,
    blood: LastBlood,
    capacity: int = 4,
) -> SeasonPlan:
    """Move one dam from a replaceable sire onto each last-carrier sire on the bench.

    Does not add a second booking to a dam. Steals from a sire that already
    has two or more dams, preferring sires that are not themselves last
    carriers. BLOCK stays refused. Capacity of the rescue sire is 1.
    """
    sitting = [c for c in blood.sitting_out if c.sex == "M"]
    if not sitting:
        return plan
    last_ids = {c.animal_id for c in blood.cards if c.irreplaceable}
    assignments = list(plan.assignments)
    used: dict[str, int] = {}
    for a in assignments:
        used[a.sire_id] = used.get(a.sire_id, 0) + 1

    for card in sitting:
        legal = {
            p.dam_id: p
            for p in pairs
            if p.sire_id == card.animal_id and p.verdict != "BLOCK"
        }
        if not legal:
            continue
        victims = [
            a
            for a in assignments
            if a.dam_id in legal
            and a.sire_id != card.animal_id
            and used.get(a.sire_id, 0) >= 2
        ]
        if not victims:
            continue

        def steal_key(a: Assignment) -> tuple:
            pick = legal[a.dam_id]
            replaceable = 0 if a.sire_id not in last_ids else 1
            return (replaceable, -used.get(a.sire_id, 0), pick.F, a.dam_name)

        victim = min(victims, key=steal_key)
        pick = legal[victim.dam_id]
        used[victim.sire_id] -= 1
        used[card.animal_id] = used.get(card.animal_id, 0) + 1
        carried = ", ".join(card.last_of[:3])
        extra = f" (+{len(card.last_of) - 3} more)" if len(card.last_of) > 3 else ""
        rescued = Assignment(
            dam_id=pick.dam_id,
            sire_id=pick.sire_id,
            dam_name=pick.dam_name,
            sire_name=pick.sire_name,
            F=pick.F,
            f_pct=pick.f_pct,
            verdict=pick.verdict,
            reason=(
                f"rescue: last carrier of {carried}{extra}; "
                f"F={pick.f_pct:.2f}% {pick.verdict}"
            ),
            year=plan.year,
        )
        assignments = [
            rescued if a.dam_id == victim.dam_id else a for a in assignments
        ]

    mean_f = sum(a.F for a in assignments) / len(assignments) if assignments else 0.0
    used_sires = {
        herd.animals[s].name: n for s, n in used.items() if n and s in herd.animals
    }
    assignments.sort(key=lambda a: (a.sire_name, a.dam_name))
    return SeasonPlan(
        year=plan.year,
        assignments=assignments,
        unassigned=list(plan.unassigned),
        mean_f=mean_f,
        used_sires=used_sires,
        bench=_bench(pairs, herd, engine, used, capacity),
    )


def last_blood(
    herd: HerdGraph,
    engine: WrightEngine,
    plan: SeasonPlan | None = None,
    pairs: list[Pair] | None = None,
    min_share: float = MIN_SHARE,
) -> LastBlood:
    registered = [rid for rid in herd.registered_ids if rid in herd.animals]
    shares: dict[str, dict[str, float]] = {
        rid: expected_founder_contributions(rid, herd) for rid in registered
    }

    founder_ids: set[str] = set()
    for smap in shares.values():
        founder_ids.update(fid for fid in smap if _is_real_founder(fid))

    n = len(registered) or 1
    risks: list[FounderRisk] = []
    for fid in founder_ids:
        carriers: list[Carrier] = []
        herd_share = 0.0
        for rid in registered:
            val = shares[rid].get(fid, 0.0)
            herd_share += val
            if val >= min_share:
                node = herd.animals[rid]
                carriers.append(
                    Carrier(
                        animal_id=rid,
                        name=node.name,
                        sex=node.sex,
                        share=val,
                        share_pct=round(val * 100.0, 2),
                    )
                )
        carriers.sort(key=lambda c: -c.share)
        if 1 <= len(carriers) <= RARE_CARRIER_MAX:
            risks.append(
                FounderRisk(
                    founder_id=fid,
                    founder_name=_name(herd, fid),
                    n_carriers=len(carriers),
                    last=len(carriers) == 1,
                    carriers=carriers,
                    herd_share=herd_share / n,
                )
            )
    risks.sort(key=lambda r: (r.n_carriers, -r.herd_share, r.founder_name))

    last_of: dict[str, list[str]] = {rid: [] for rid in registered}
    rare_of: dict[str, list[str]] = {rid: [] for rid in registered}
    uniqueness: dict[str, float] = {rid: 0.0 for rid in registered}
    for risk in risks:
        for c in risk.carriers:
            rare_of[c.animal_id].append(risk.founder_name)
            uniqueness[c.animal_id] += c.share
            if risk.last:
                last_of[c.animal_id].append(risk.founder_name)

    booked: set[str] = set()
    if plan:
        for a in plan.assignments:
            booked.add(a.dam_id)
            booked.add(a.sire_id)

    cards: list[SalvageCard] = []
    for rid in registered:
        if not rare_of[rid] and uniqueness[rid] <= 0:
            continue
        node = herd.animals[rid]
        mk = engine.mean_kinship(rid, registered)
        irrep = bool(last_of[rid])
        in_plan = rid in booked
        why = _why(node.name, last_of[rid], rare_of[rid], in_plan, irrep)
        cards.append(
            SalvageCard(
                animal_id=rid,
                name=node.name,
                sex=node.sex,
                mk=mk,
                mk_pct=round(mk * 100.0, 2),
                uniqueness=uniqueness[rid],
                uniqueness_pct=round(uniqueness[rid] * 100.0, 2),
                last_of=last_of[rid],
                rare_of=rare_of[rid],
                in_year1_plan=in_plan,
                irreplaceable=irrep,
                why=why,
            )
        )
    cards.sort(key=lambda c: (-c.irreplaceable, -c.uniqueness, c.name))
    sitting = [c for c in cards if c.irreplaceable and not c.in_year1_plan]
    last_founders = [r for r in risks if r.last]
    return LastBlood(
        rare_founders=risks,
        last_founders=last_founders,
        cards=cards,
        sitting_out=sitting,
        rescue=rescue_bookings(sitting, pairs),
        n_irreplaceable=sum(1 for c in cards if c.irreplaceable),
        n_rare_founders=len(risks),
        n_last_founders=len(last_founders),
        threshold=min_share,
    )


def _why(
    name: str,
    last: list[str],
    rare: list[str],
    in_plan: bool,
    irreplaceable: bool,
) -> str:
    if irreplaceable:
        carried = ", ".join(last[:3])
        extra = f" (+{len(last) - 3} more)" if len(last) > 3 else ""
        base = f"{name} is the last living carrier of {carried}{extra}."
        if not in_plan:
            return base + " Not in the year-1 plan — this blood sits out."
        return base + " Already booked this season."
    carried = ", ".join(rare[:3])
    extra = f" (+{len(rare) - 3} more)" if len(rare) > 3 else ""
    return f"{name} is one of two living carriers of {carried}{extra}."
