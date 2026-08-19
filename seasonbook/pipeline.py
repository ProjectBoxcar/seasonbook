"""Build the full season snapshot from the certificate directory."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .census import Census, build_census
from .erode import Erosion, erode
from .gate import TheGate, the_gate
from .parse import HerdGraph, ingest_dir
from .next import NextNucleus, next_nucleus
from .wean import WeaningLedger, weaning_ledger
from .plan import (
    Audit,
    SeasonPlan,
    all_pairs,
    assign_season,
    audit_pairs,
    coverage_table,
    dam_bottlenecks,
    projected_cria_f,
    rotate_from_year1,
)
from .salvage import LastBlood, apply_rescue, last_blood
from .wright import DEFAULT_PEDIGREE_DEPTH, WrightEngine

DEFAULT_CERT_DIR = (
    Path(__file__).resolve().parents[2] / "AlpacaManager" / "docs" / "cert_lineage"
)
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "output"


@dataclass
class Snapshot:
    built: str
    cert_dir: str
    n_certificates: int
    herd: HerdGraph
    engine: WrightEngine
    census: Census
    pairs: list
    audit: Audit
    plan: SeasonPlan
    rotation: list[SeasonPlan]
    coverage: list
    bottlenecks: list
    trajectory: list
    last_blood: LastBlood
    erosion: Erosion
    gate: TheGate
    wean: WeaningLedger
    nxt: NextNucleus

    def briefing(self) -> dict:
        c = self.census
        return {
            "built": self.built,
            "certificates": self.n_certificates,
            "animals": c.n_animals,
            "registered": c.n_registered,
            "founders": c.n_founders,
            "dams": c.n_dams,
            "sires": c.n_sires,
            "unsexed": c.n_unsexed,
            "mean_f_pct": round(c.mean_f * 100.0, 2),
            "max_f_pct": round(c.max_f * 100.0, 2),
            "max_f_name": c.max_f_name,
            "mean_mk_pct": round(c.mean_mk * 100.0, 2),
            "founder_genome_equivalents": round(c.founder_genome_equivalents, 2),
            "effective_size": round(c.effective_size, 1),
            "plan_n": len(self.plan.assignments),
            "plan_mean_f_pct": round(self.plan.mean_f * 100.0, 2),
            "plan_sires": len(self.plan.used_sires),
            "blocks": self.audit.n_block,
            "confirms": self.audit.n_confirm,
            "proceed": self.audit.n_proceed,
            "thin_pedigrees": c.thin_pedigrees,
            "irreplaceable": self.last_blood.n_irreplaceable,
            "last_founders": self.last_blood.n_last_founders,
            "rare_founders": self.last_blood.n_rare_founders,
            "sitting_out": len(self.last_blood.sitting_out),
            "rescued": sum(1 for a in self.plan.assignments if a.reason.startswith("rescue:")),
            "habit_lost_founders": len(self.erosion.lost_to_habit),
            "rotation_saves": len(self.erosion.saved_by_rotation),
            "keep": self.gate.n_keep,
            "keep_until": self.gate.n_keep_until,
            "wait": self.gate.n_wait,
            "let_go": self.gate.n_let_go,
            "pair_locks": len(self.gate.pair_locks),
            "last_founders_after": self.gate.after.n_last_founders_after,
            "rescued_founders": len(self.gate.after.rescued_founders),
            "wean_cover": self.wean.n_cover,
            "wean_sellable": self.wean.n_sellable_cria,
            "wean_release": self.wean.n_release,
            "wean_uncovered": self.wean.n_uncovered,
            "next_collisions": self.nxt.n_collisions,
            "next_band_n": self.nxt.band.n,
            "next_band_year2": self.nxt.band.n_year2,
            "next_shrink_n": self.nxt.shrink.n,
            "next_shrink_year2": self.nxt.shrink.n_year2,
            "next_core": self.nxt.n_core,
            "next_finish_year2": self.nxt.finish.n_year2,
        }


def build_from_herd(
    herd: HerdGraph,
    max_gen: int = DEFAULT_PEDIGREE_DEPTH,
    capacity: int = 4,
    source_label: str = "",
) -> Snapshot:
    """Same snapshot pipeline, starting from an already-built graph.

    AlpacaManager calls this after mapping SQLite rows. The offline desk
    calls it after ingesting cert_lineage markdown.
    """
    engine = WrightEngine(herd.to_pedigree(), max_gen=max_gen)
    census = build_census(herd, engine)
    pairs = all_pairs(herd, engine)
    audit = audit_pairs(pairs)
    raw_plan = assign_season(pairs, herd, engine, capacity=capacity, year=1)
    draft_blood = last_blood(herd, engine, raw_plan, pairs=pairs)
    plan = apply_rescue(raw_plan, pairs, herd, engine, draft_blood, capacity=capacity)
    rotation = rotate_from_year1(plan, pairs, herd, engine, capacity=capacity)
    rescued_rot = [rotation[0]]
    for later in rotation[1:]:
        later_blood = last_blood(herd, engine, later, pairs=pairs)
        rescued_rot.append(
            apply_rescue(later, pairs, herd, engine, later_blood, capacity=capacity)
        )
    rotation = rescued_rot
    coverage = coverage_table(pairs, herd, engine, plan)
    bottlenecks = dam_bottlenecks(pairs, herd)
    trajectory = projected_cria_f(rotation)
    blood = last_blood(herd, engine, plan, pairs=pairs)
    erosion = erode(pairs, herd, engine, capacity=capacity, years=5)
    gate = the_gate(herd, engine, plan)
    wean = weaning_ledger(herd, engine, plan, gate)
    nxt = next_nucleus(
        herd, engine, plan, rotation, gate, wean, pairs=pairs, capacity=capacity
    )
    return Snapshot(
        built=date.today().isoformat(),
        cert_dir=source_label,
        n_certificates=len(herd.sources),
        herd=herd,
        engine=engine,
        census=census,
        pairs=pairs,
        audit=audit,
        plan=plan,
        rotation=rotation,
        coverage=coverage,
        bottlenecks=bottlenecks,
        trajectory=trajectory,
        last_blood=blood,
        erosion=erosion,
        gate=gate,
        wean=wean,
        nxt=nxt,
    )


def build(
    cert_dir: Path | None = None,
    max_gen: int = DEFAULT_PEDIGREE_DEPTH,
    capacity: int = 4,
) -> Snapshot:
    cert_dir = Path(cert_dir) if cert_dir else DEFAULT_CERT_DIR
    herd = ingest_dir(cert_dir)
    return build_from_herd(
        herd,
        max_gen=max_gen,
        capacity=capacity,
        source_label=str(cert_dir),
    )


def snapshot_dict(snap: Snapshot) -> dict:
    def pair_d(p):
        return {
            "dam_id": p.dam_id,
            "sire_id": p.sire_id,
            "dam_name": p.dam_name,
            "sire_name": p.sire_name,
            "F": p.F,
            "f_pct": p.f_pct,
            "verdict": p.verdict,
            "structural": p.structural,
            "top_ancestor": p.top_ancestor,
            "top_contrib_pct": p.top_contrib_pct,
        }

    def asg_d(a):
        return {
            "dam_id": a.dam_id,
            "sire_id": a.sire_id,
            "dam_name": a.dam_name,
            "sire_name": a.sire_name,
            "F": a.F,
            "f_pct": a.f_pct,
            "verdict": a.verdict,
            "reason": a.reason,
            "year": a.year,
        }

    cards = [asdict(c) for c in snap.census.cards]
    founders = [asdict(f) for f in snap.census.founders[:40]]
    presence = [asdict(f) for f in snap.census.presence[:30]]
    return {
        "briefing": snap.briefing(),
        "cards": cards,
        "founders": founders,
        "presence": presence,
        "plan": {
            "year": snap.plan.year,
            "mean_f_pct": round(snap.plan.mean_f * 100.0, 2),
            "assignments": [asg_d(a) for a in snap.plan.assignments],
            "unassigned": snap.plan.unassigned,
            "used_sires": snap.plan.used_sires,
            "bench": snap.plan.bench,
        },
        "rotation": [
            {
                "year": p.year,
                "mean_f_pct": round(p.mean_f * 100.0, 2),
                "assignments": [asg_d(a) for a in p.assignments],
                "used_sires": p.used_sires,
                "unassigned": p.unassigned,
            }
            for p in snap.rotation
        ],
        "trajectory": snap.trajectory,
        "audit": {
            "n_block": snap.audit.n_block,
            "n_confirm": snap.audit.n_confirm,
            "n_proceed": snap.audit.n_proceed,
            "blocks": [pair_d(p) for p in snap.audit.blocks],
            "confirms": [pair_d(p) for p in snap.audit.confirms],
        },
        "coverage": [asdict(r) for r in snap.coverage],
        "bottlenecks": snap.bottlenecks,
        "last_blood": snap.last_blood.as_dict(),
        "erosion": snap.erosion.as_dict(),
        "gate": snap.gate.as_dict(),
        "wean": snap.wean.as_dict(),
        "next": snap.nxt.as_dict(),
        "heatmap": _heatmap(snap),
        "animals": [
            {
                "id": a.id,
                "name": a.name,
                "sex": a.sex,
                "color": a.color,
                "registered": a.registered,
                "sire_name": a.sire_name,
                "dam_name": a.dam_name,
                "f_pct": a.f_pct,
                "mk_pct": a.mk_pct,
                "ecg": a.ecg,
            }
            for a in snap.census.cards
        ],
    }


def _heatmap(snap: Snapshot) -> dict:
    dams = sorted(
        {p.dam_name for p in snap.pairs},
    )
    sires = sorted({p.sire_name for p in snap.pairs})
    # keep a stable, readable order: dams by name, sires by MK then name
    mk = {r.sire_name: r.mk_pct for r in snap.coverage}
    sires = sorted(sires, key=lambda n: (mk.get(n, 99), n))
    dam_ids = {}
    sire_ids = {}
    for p in snap.pairs:
        dam_ids[p.dam_name] = p.dam_id
        sire_ids[p.sire_name] = p.sire_id
    cells = []
    by = {(p.dam_name, p.sire_name): p for p in snap.pairs}
    for d in dams:
        row = []
        for s in sires:
            p = by[(d, s)]
            row.append(
                {
                    "f_pct": p.f_pct,
                    "verdict": p.verdict,
                    "structural": p.structural,
                    "top": p.top_ancestor,
                }
            )
        cells.append(row)
    return {"dams": dams, "sires": sires, "cells": cells}


def write_snapshot(snap: Snapshot, out_dir: Path | None = None) -> Path:
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "snapshot.json"
    path.write_text(json.dumps(snapshot_dict(snap), indent=2), encoding="utf-8")
    return path
