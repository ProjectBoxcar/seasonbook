"""Founder census, mean kinship, and effective size of the registered nucleus.

Expected founder contribution is the Mendelian 50/50 walk to animals with
no recorded parents. Presence is coarser: the fraction of registered
pedigrees that contain the ancestor at all.

Effective size follows Caballero & Toro: founder-genome equivalents
fge = 1 / (2 · mean coancestry), using the kinship matrix of the
registered animals including the diagonal θ_ii = (1+F_i)/2.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .parse import HerdGraph
from .wright import WrightEngine, completeness, interpret_f, iter_ancestors


@dataclass
class AnimalCard:
    id: str
    name: str
    sex: str | None
    color: str | None
    registered: bool
    sire_id: str | None
    dam_id: str | None
    sire_name: str | None
    dam_name: str | None
    F: float
    f_pct: float
    f_level: str
    mk: float
    mk_pct: float
    completeness_index: float
    ecg: float
    may_underestimate_f: bool
    founder_count: int


@dataclass
class FounderShare:
    id: str
    name: str
    contribution: float
    presence: int
    presence_pct: float
    still_segregating: bool = True


@dataclass
class Census:
    n_animals: int
    n_registered: int
    n_founders: int
    n_dams: int
    n_sires: int
    n_unsexed: int
    mean_f: float
    max_f: float
    max_f_name: str
    mean_mk: float
    mean_coancestry_incl: float
    founder_genome_equivalents: float
    effective_size: float
    cards: list[AnimalCard]
    founders: list[FounderShare]
    presence: list[FounderShare]
    thin_pedigrees: list[str]


def _name(herd: HerdGraph, ident: str | None) -> str | None:
    if not ident:
        return None
    node = herd.animals.get(ident)
    return node.name if node else ident


def expected_founder_contributions(animal_id: str, herd: HerdGraph) -> dict[str, float]:
    """Mendelian expected share of each founder in one animal."""
    cache: dict[str, dict[str, float]] = {}

    def walk(ident: str) -> dict[str, float]:
        hit = cache.get(ident)
        if hit is not None:
            return hit
        node = herd.animals.get(ident)
        if node is None or (not node.sire_key and not node.dam_key):
            result = {ident: 1.0}
            cache[ident] = result
            return result
        acc: dict[str, float] = defaultdict(float)
        parents = [p for p in (node.sire_key, node.dam_key) if p]
        # Unknown parent is its own founder slot
        if node.sire_key is None:
            acc[f"UNK-SIRE:{ident}"] += 0.5
        if node.dam_key is None:
            acc[f"UNK-DAM:{ident}"] += 0.5
        share = 0.5
        for parent in parents:
            for founder, val in walk(parent).items():
                acc[founder] += share * val
        result = dict(acc)
        cache[ident] = result
        return result

    return walk(animal_id)


def build_census(herd: HerdGraph, engine: WrightEngine) -> Census:
    registered = [rid for rid in herd.registered_ids if rid in herd.animals]
    cards: list[AnimalCard] = []
    founder_sum: dict[str, float] = defaultdict(float)
    presence_count: dict[str, int] = defaultdict(int)
    thin: list[str] = []

    for rid in registered:
        node = herd.animals[rid]
        f = engine.f(rid)
        level, pct, _ = interpret_f(f)
        mk = engine.mean_kinship(rid, registered)
        comp = completeness(rid, node.sire_key, node.dam_key, engine.pedigree, engine.max_gen)
        if comp["may_underestimate_f"] and f < 0.0625:
            thin.append(node.name)
        ancestors = set(iter_ancestors(rid, engine.pedigree))
        for anc in ancestors:
            presence_count[anc] += 1
        shares = expected_founder_contributions(rid, herd)
        for founder, val in shares.items():
            founder_sum[founder] += val
        cards.append(
            AnimalCard(
                id=rid,
                name=node.name,
                sex=node.sex,
                color=node.color,
                registered=True,
                sire_id=node.sire_key,
                dam_id=node.dam_key,
                sire_name=_name(herd, node.sire_key),
                dam_name=_name(herd, node.dam_key),
                F=f,
                f_pct=pct,
                f_level=level,
                mk=mk,
                mk_pct=round(mk * 100.0, 2),
                completeness_index=comp["index"],
                ecg=comp["equivalent_complete_generations"],
                may_underestimate_f=comp["may_underestimate_f"],
                founder_count=len(shares),
            )
        )

    n = len(registered) or 1
    founders: list[FounderShare] = []
    for fid, total in founder_sum.items():
        node = herd.animals.get(fid)
        name = node.name if node else fid
        founders.append(
            FounderShare(
                id=fid,
                name=name,
                contribution=total / n,
                presence=presence_count.get(fid, 0),
                presence_pct=round(100.0 * presence_count.get(fid, 0) / n, 1),
            )
        )
    founders.sort(key=lambda x: x.contribution, reverse=True)

    presence: list[FounderShare] = []
    for aid, count in presence_count.items():
        node = herd.animals.get(aid)
        name = node.name if node else aid
        # contribution here unused; filled with 0
        presence.append(
            FounderShare(
                id=aid,
                name=name,
                contribution=0.0,
                presence=count,
                presence_pct=round(100.0 * count / n, 1),
            )
        )
    presence.sort(key=lambda x: x.presence, reverse=True)

    # Kinship of the registered nucleus
    matrix = engine.kinship_matrix(registered)
    off = []
    incl = []
    for i in range(len(registered)):
        for j in range(len(registered)):
            incl.append(matrix[i][j])
            if i < j:
                off.append(matrix[i][j])
    mean_mk = sum(off) / len(off) if off else 0.0
    mean_incl = sum(incl) / len(incl) if incl else 0.0
    fge = (1.0 / (2.0 * mean_incl)) if mean_incl > 0 else float("inf")
    ne = (1.0 / (2.0 * mean_mk)) if mean_mk > 0 else float("inf")

    dams = [c for c in cards if c.sex == "F"]
    sires = [c for c in cards if c.sex == "M"]
    unsexed = [c for c in cards if c.sex not in {"M", "F"}]
    mean_f = sum(c.F for c in cards) / n
    top = max(cards, key=lambda c: c.F) if cards else None

    n_founders = sum(
        1
        for a in herd.animals.values()
        if a.sire_key is None and a.dam_key is None
    )

    return Census(
        n_animals=len(herd.animals),
        n_registered=len(registered),
        n_founders=n_founders,
        n_dams=len(dams),
        n_sires=len(sires),
        n_unsexed=len(unsexed),
        mean_f=mean_f,
        max_f=top.F if top else 0.0,
        max_f_name=top.name if top else "",
        mean_mk=mean_mk,
        mean_coancestry_incl=mean_incl,
        founder_genome_equivalents=fge,
        effective_size=ne,
        cards=sorted(cards, key=lambda c: (-c.F, c.name)),
        founders=founders,
        presence=presence,
        thin_pedigrees=thin,
    )
