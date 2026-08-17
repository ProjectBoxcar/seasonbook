"""Barn-language Wright stories for a single pairing or animal."""

from __future__ import annotations

from .parse import HerdGraph
from .wright import (
    WrightEngine,
    analyze_inbreeding,
    completeness,
    interpret_f,
    structural_relationship,
    verdict_for,
    wright_paths,
)


def _nm(herd: HerdGraph, ident: str) -> str:
    node = herd.animals.get(ident)
    return node.name if node else ident


def find_animal(herd: HerdGraph, query: str) -> str | None:
    q = (query or "").strip().upper()
    if not q:
        return None
    if q in herd.animals:
        return q
    hits = []
    for aid, node in herd.animals.items():
        name = node.name.upper()
        if name == q or q in name or name in q:
            hits.append(aid)
    if len(hits) == 1:
        return hits[0]
    # prefer registered
    reg = [h for h in hits if herd.animals[h].registered]
    if len(reg) == 1:
        return reg[0]
    if reg:
        return min(reg, key=lambda h: len(herd.animals[h].name))
    if hits:
        return min(hits, key=lambda h: len(herd.animals[h].name))
    return None


def explain_pair(herd: HerdGraph, engine: WrightEngine, dam_q: str, sire_q: str) -> dict:
    dam_id = find_animal(herd, dam_q)
    sire_id = find_animal(herd, sire_q)
    if not dam_id or not sire_id:
        return {"ok": False, "error": f"not found: dam={dam_q!r} sire={sire_q!r}"}
    f, hits = wright_paths(dam_id, sire_id, engine.pedigree, engine.max_gen, engine)
    structural = structural_relationship(dam_id, sire_id, engine.pedigree)
    verdict = verdict_for(f, structural)
    level, pct, summary = interpret_f(f)
    dam = herd.animals[dam_id]
    sire = herd.animals[sire_id]
    comp = completeness(
        f"{dam_id}×{sire_id}",
        sire_id,
        dam_id,
        engine.pedigree,
        engine.max_gen,
    )
    ancestors = []
    attributed = 0.0
    for hit in hits[:8]:
        attributed += hit.contribution
        paths = []
        for pa in hit.paths_from_a[:3]:
            paths.append(" → ".join(_nm(herd, x) for x in pa.path))
        for pb in hit.paths_from_b[:3]:
            paths.append(" → ".join(_nm(herd, x) for x in pb.path))
        ancestors.append(
            {
                "name": _nm(herd, hit.ancestor_id),
                "contribution_pct": round(hit.contribution * 100.0, 2),
                "share_of_f": round(100.0 * hit.contribution / f, 1) if f else 0.0,
                "ancestor_f_pct": round(hit.ancestor_f * 100.0, 2),
                "paths": paths[:6],
            }
        )
    story = _story(dam.name, sire.name, f, verdict, structural, ancestors, comp)
    return {
        "ok": True,
        "dam": dam.name,
        "sire": sire.name,
        "F": f,
        "f_pct": pct,
        "level": level,
        "verdict": verdict,
        "structural": structural,
        "summary": summary,
        "story": story,
        "ancestors": ancestors,
        "attributed_share_of_f": round(attributed / f, 3) if f else 1.0,
        "completeness": comp,
    }


def explain_animal(herd: HerdGraph, engine: WrightEngine, query: str) -> dict:
    aid = find_animal(herd, query)
    if not aid:
        return {"ok": False, "error": f"not found: {query!r}"}
    node = herd.animals[aid]
    result = analyze_inbreeding(aid, engine.pedigree, engine.max_gen, engine)
    mk = engine.mean_kinship(aid, herd.registered_ids)
    comp = completeness(aid, node.sire_key, node.dam_key, engine.pedigree, engine.max_gen)
    ancestors = []
    for hit in result.common_ancestors[:8]:
        ancestors.append(
            {
                "name": _nm(herd, hit.ancestor_id),
                "contribution_pct": round(hit.contribution * 100.0, 2),
                "ancestor_f_pct": round(hit.ancestor_f * 100.0, 2),
            }
        )
    return {
        "ok": True,
        "id": aid,
        "name": node.name,
        "sex": node.sex,
        "color": node.color,
        "registered": node.registered,
        "sire": _nm(herd, node.sire_key) if node.sire_key else None,
        "dam": _nm(herd, node.dam_key) if node.dam_key else None,
        "F": result.F,
        "f_pct": result.percent,
        "level": result.level,
        "summary": result.summary,
        "mk_pct": round(mk * 100.0, 2),
        "ancestors": ancestors,
        "completeness": comp,
    }


def _story(dam, sire, f, verdict, structural, ancestors, comp) -> str:
    pct = f * 100.0
    if structural == "parent_offspring":
        head = (
            f"{dam} × {sire} is parent × offspring. "
            f"F = {pct:.2f}% (25% plus any extra from the parent's own inbreeding). BLOCK."
        )
    elif structural == "full_sib":
        head = f"{dam} × {sire} are full siblings. F = {pct:.2f}%. BLOCK."
    elif verdict == "BLOCK":
        head = f"{dam} × {sire} lands at F = {pct:.2f}%. That is close-kin territory. BLOCK."
    elif verdict == "CONFIRM":
        head = (
            f"{dam} × {sire} is not a parent-child mating, but F = {pct:.2f}% "
            "is half-sib / grandparent range. CONFIRM before you book it."
        )
    elif pct < 0.5:
        head = (
            f"{dam} × {sire} has no close common ancestor in the recorded pedigree "
            f"(F = {pct:.2f}%). PROCEED on F alone."
        )
    else:
        head = f"{dam} × {sire} is legal on F = {pct:.2f}%. PROCEED."
    if ancestors and f >= 0.01:
        top = ancestors[0]
        head += (
            f" The number is pushed hardest by {top['name']} "
            f"({top['share_of_f']:.0f}% of F)."
        )
    if comp.get("may_underestimate_f") and f < 0.0625:
        head += (
            " Pedigree is thin — a low F here is a floor, not proof of an outcross."
        )
    return head
