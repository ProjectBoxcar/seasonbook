"""python -m seasonbook {analyze|plan|audit|explain|why|cover|kinship|horizon|book|serve}"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .book import write_all_pdfs
from .explain import explain_animal, explain_pair
from .pipeline import DEFAULT_CERT_DIR, DEFAULT_OUT, build, write_snapshot
from .serve import serve


def _snap(args):
    return build(cert_dir=args.certs, max_gen=args.depth, capacity=args.capacity)


def cmd_analyze(args) -> int:
    snap = _snap(args)
    b = snap.briefing()
    print("SEASON BOOK  ·  registered nucleus")
    print(f"  certificates     {b['certificates']}")
    print(f"  animals          {b['animals']}  ({b['founders']} founders)")
    print(f"  registered       {b['registered']}  ·  {b['dams']} dams  ·  {b['sires']} sires  ·  {b['unsexed']} unsexed")
    print(f"  mean F           {b['mean_f_pct']:.2f}%   max {b['max_f_pct']:.2f}%  ({b['max_f_name']})")
    print(f"  mean MK          {b['mean_mk_pct']:.2f}%")
    print(f"  Ne               {b['effective_size']:.1f}")
    print(f"  founder genomes  {b['founder_genome_equivalents']:.2f}")
    print()
    print("Hottest registered (own F)")
    for card in snap.census.cards[:8]:
        print(f"  {card.f_pct:5.2f}%  {card.sex or '?'}  {card.name}   MK {card.mk_pct:.2f}%")
    print()
    print("Top founder shares")
    for f in snap.census.founders[:8]:
        print(f"  {f.contribution*100:5.2f}%  {f.name}   in {f.presence}/{b['registered']} pedigrees")
    print()
    print("Most present ancestors (presence ≠ share)")
    for f in snap.census.presence[:8]:
        print(f"  {f.presence:2d}/{b['registered']}  {f.name}")
    if args.json:
        path = write_snapshot(snap, args.out)
        print(f"\nwrote {path}")
    return 0


def cmd_plan(args) -> int:
    snap = _snap(args)
    p = snap.plan
    print(f"YEAR 1  ·  {len(p.assignments)} bookings  ·  mean F {p.mean_f*100:.2f}%")
    if p.unassigned:
        print("  unassigned:", ", ".join(p.unassigned))
    print(f"  sires used ({len(p.used_sires)}):")
    for name, n in sorted(p.used_sires.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"    {n}×  {name}")
    print()
    for a in p.assignments:
        print(f"  {a.dam_name:32s}  ×  {a.sire_name:28s}  F={a.f_pct:5.2f}%  {a.verdict}")
        print(f"      {a.reason}")
    return 0


def cmd_audit(args) -> int:
    snap = _snap(args)
    a = snap.audit
    print(f"AUDIT  {a.n_block} BLOCK  ·  {a.n_confirm} CONFIRM  ·  {a.n_proceed} PROCEED")
    print("\nBLOCK")
    for p in a.blocks:
        tag = (p.structural or "").replace("_", " ")
        print(f"  {p.f_pct:5.2f}%  {p.dam_name}  ×  {p.sire_name}   {tag}")
    print("\nCONFIRM")
    for p in a.confirms:
        via = f"  via {p.top_ancestor}" if p.top_ancestor else ""
        print(f"  {p.f_pct:5.2f}%  {p.dam_name}  ×  {p.sire_name}{via}")
    return 0


def cmd_explain(args) -> int:
    snap = _snap(args)
    if args.sire:
        result = explain_pair(snap.herd, snap.engine, args.animal, args.sire)
    else:
        result = explain_animal(snap.herd, snap.engine, args.animal)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


def cmd_why(args) -> int:
    snap = _snap(args)
    result = explain_animal(snap.herd, snap.engine, args.animal)
    if not result.get("ok"):
        print(result.get("error"))
        return 2
    print(f"{result['name']}  {result.get('sex') or '?'}  F={result['f_pct']}%  MK={result['mk_pct']}%")
    print(result["summary"])
    if result.get("sire") or result.get("dam"):
        print(f"  sire {result.get('sire')}  ·  dam {result.get('dam')}")
    for anc in result.get("ancestors") or []:
        print(f"  {anc['contribution_pct']:5.2f} pt  {anc['name']}  (own F {anc['ancestor_f_pct']}%)")
    cover = next((r for r in snap.coverage if r.sire_name.upper() == result["name"].upper()), None)
    if cover:
        print(cover.why)
        print(f"  legal {cover.legal}  block {cover.block}  booked {cover.assigned}")
    return 0


def cmd_cover(args) -> int:
    snap = _snap(args)
    print(f"{'SIRE':32s} {'MK':>6} {'LEGAL':>6} {'BLK':>4} {'CNF':>4} {'IN':>3}  WHY")
    for r in snap.coverage:
        if args.sire and args.sire.lower() not in r.sire_name.lower():
            continue
        print(
            f"{r.sire_name:32s} {r.mk_pct:5.2f}% {r.legal:6d} {r.block:4d} {r.confirm:4d} {r.assigned:3d}  {r.why}"
        )
    return 0


def cmd_kinship(args) -> int:
    snap = _snap(args)
    print("Mean kinship of registered animals (hottest first)")
    cards = sorted(snap.census.cards, key=lambda c: -c.mk)
    for c in cards:
        print(f"  {c.mk_pct:5.2f}%  {c.sex or '?'}  {c.name}")
    print(f"\nmean pairwise MK {snap.census.mean_mk*100:.2f}%")
    print(f"Ne {snap.census.effective_size:.1f}   fge {snap.census.founder_genome_equivalents:.2f}")
    return 0


def cmd_horizon(args) -> int:
    snap = _snap(args)
    for plan in snap.rotation:
        print(f"YEAR {plan.year}  ·  {len(plan.assignments)}  ·  mean F {plan.mean_f*100:.2f}%")
        print("  " + ", ".join(f"{n}×{c}" for n, c in sorted(plan.used_sires.items())))
        for a in plan.assignments:
            print(f"    {a.dam_name:32s} × {a.sire_name:28s}  {a.f_pct:5.2f}%")
        print()
    print("Projected cria F:", "  ".join(
        f"Y{t['year']} {t['mean_f']*100:.2f}%" for t in snap.trajectory
    ))
    return 0


def cmd_book(args) -> int:
    snap = _snap(args)
    write_snapshot(snap, args.out)
    paths = write_all_pdfs(snap, args.out)
    for p in paths:
        print("wrote", p)
    return 0


def cmd_serve(args) -> int:
    snap = _snap(args)
    write_snapshot(snap, args.out)
    write_all_pdfs(snap, args.out)
    serve(snap, host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="seasonbook",
        description="Season Book — Wright genetics on the real AOA certificates.",
    )
    parser.add_argument("--certs", type=Path, default=DEFAULT_CERT_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--depth", type=int, default=6)
    parser.add_argument("--capacity", type=int, default=4)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("analyze", help="herd briefing")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("plan", help="year-1 assignment")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("audit", help="close-kin BLOCK / CONFIRM")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("explain", help="Wright story of an animal or a pair")
    p.add_argument("animal")
    p.add_argument("--sire", default="")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("why", help="why this animal is hot / on the bench")
    p.add_argument("animal")
    p.set_defaults(func=cmd_why)

    p = sub.add_parser("cover", help="sire coverage table")
    p.add_argument("--sire", default="")
    p.set_defaults(func=cmd_cover)

    p = sub.add_parser("kinship", help="mean kinship ranking")
    p.set_defaults(func=cmd_kinship)

    p = sub.add_parser("horizon", help="three-season rotation")
    p.set_defaults(func=cmd_horizon)

    p = sub.add_parser("book", help="write PDFs + snapshot.json")
    p.set_defaults(func=cmd_book)

    p = sub.add_parser("serve", help="open the Command Center")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
