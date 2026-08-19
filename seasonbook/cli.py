"""python -m seasonbook {analyze|plan|audit|explain|why|cover|kinship|horizon|salvage|erode|gate|wean|next|book|serve}"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .book import (
    write_all_pdfs,
    write_board_pdf,
    write_cards_pdf,
    write_catalog_pdf,
    write_gate_pdf,
    write_next_pdf,
    write_wean_pdf,
)
from .export import tonight_lines, write_gate_csv, write_plan_csv, write_wean_csv
from .gate import KEEP, KEEP_UNTIL_WEANING, LET_GO, WAIT, explain_leave
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
    print(
        f"  last blood       {b['irreplaceable']} irreplaceable  ·  "
        f"{b['last_founders']} last founders  ·  {b['sitting_out']} sitting out  ·  "
        f"{b.get('rescued', 0)} rescued into year 1"
    )
    print(
        f"  the gate         {b.get('keep', 0)} KEEP  ·  "
        f"{b.get('keep_until', 0)} KEEP UNTIL WEANING  ·  "
        f"{b.get('wait', 0)} WAIT  ·  {b.get('let_go', 0)} LET GO  ·  "
        f"{b.get('pair_locks', 0)} pair-locks"
    )
    print(
        f"  after cria       last founders {b['last_founders']} → "
        f"{b.get('last_founders_after', '—')}  ·  "
        f"{b.get('rescued_founders', 0)} duplicated by the crop"
    )
    print(
        f"  wean             keep {b.get('wean_cover', 0)} cria  ·  "
        f"{b.get('wean_release', 0)} parents may list  ·  "
        f"{b.get('wean_sellable', 0)} sellable weanlings  ·  "
        f"{b.get('wean_uncovered', 0)} uncovered"
    )
    print(
        f"  next             {b.get('next_collisions', 0)} collisions  ·  "
        f"band {b.get('next_band_n', '—')} living / Y2 {b.get('next_band_year2', '—')}  ·  "
        f"shrink {b.get('next_shrink_n', '—')} living / Y2 {b.get('next_shrink_year2', '—')}"
    )
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


def cmd_salvage(args) -> int:
    snap = _snap(args)
    lb = snap.last_blood
    print(
        f"LAST BLOOD  {lb.n_irreplaceable} irreplaceable  ·  "
        f"{lb.n_last_founders} last founders  ·  "
        f"{lb.n_rare_founders} rare (≤2 carriers, share ≥ {lb.threshold*100:.1f}%)"
    )
    if lb.sitting_out:
        print("\nSitting out this season (last carrier, not booked)")
        for c in lb.sitting_out:
            print(f"  {c.uniqueness_pct:5.2f}% unique  {c.sex or '?'}  {c.name}")
            print(f"      {c.why}")
    if lb.rescue:
        print("\nRescue bookings (one legal dam, lowest F, keeps last blood)")
        for r in lb.rescue:
            print(f"  {r['sire_name']}  ×  {r['dam_name']}  F={r['f_pct']:.2f}%")
            print(f"      {r['why']}")
    print("\nIrreplaceable animals")
    for c in lb.cards:
        if not c.irreplaceable:
            continue
        flag = "BOOKED" if c.in_year1_plan else "SITS OUT"
        print(f"  {c.uniqueness_pct:5.2f}%  {c.sex or '?'}  {c.name:32s}  {flag}")
        print(f"      last of: {', '.join(c.last_of[:6])}")
    print("\nLast founders (one living carrier)")
    for f in lb.last_founders[:24]:
        carrier = f.carriers[0]
        print(
            f"  {f.founder_name:32s}  →  {carrier.name}  ({carrier.share_pct:.1f}%)"
        )
    return 0


def cmd_erode(args) -> int:
    snap = _snap(args)
    e = snap.erosion
    print(e.summary)
    print("\nYEAR   ROT F   HAB F   ROT founders   HAB founders")
    for r, h in zip(e.rotation, e.habit):
        print(
            f"  {r.year}   {r.mean_f_pct:5.2f}%  {h.mean_f_pct:5.2f}%   "
            f"{r.n_founders:4d}           {h.n_founders:4d}"
        )
    print("\nFounders the rotation keeps and habit drops")
    if not e.saved_by_rotation:
        print("  (none at the ≥3.1% threshold)")
    for row in e.saved_by_rotation[:20]:
        print(
            f"  {row.founder_name:32s}  nucleus {row.nucleus_share_pct:5.2f}%  "
            f"rotation {row.rotation_share_pct:5.2f}%  habit {row.habit_share_pct:5.2f}%"
        )
    print("\nHabit sires (hottest legal, capacity 4):", ", ".join(e.habit_sires))
    return 0


def _print_gate_card(c) -> None:
    print(f"  {c.verdict:20s}  {c.sex or '?'}  {c.name:32s}  MK {c.mk_pct:5.2f}%")
    print(f"      {c.why}")


def cmd_gate(args) -> int:
    snap = _snap(args)
    g = snap.gate
    if args.animal:
        hit = explain_leave(g, args.animal)
        if hit is None:
            print(f"no registered animal matching {args.animal!r}")
            return 2
        print(f"{hit.name}  {hit.sex or '?'}  MK {hit.mk_pct:.2f}%")
        print(hit.why)
        print(f"  Ne {hit.ne_before:.1f} → {hit.ne_after:.1f}  (Δ {hit.ne_delta:+.1f})")
        if hit.extinct_founders:
            print("  extinct:", ", ".join(hit.extinct_founders[:12]))
        if hit.new_last:
            print("  new last carriers:")
            for row in hit.new_last[:12]:
                print(f"    {row['founder_name']}  →  {row['remaining_name']}")
        if hit.new_rare:
            print("  newly rare (two left):")
            for row in hit.new_rare[:8]:
                print(f"    {row['founder_name']}  →  {', '.join(row['remaining'])}")
        return 0

    print(g.summary)
    print()
    by = {KEEP: [], KEEP_UNTIL_WEANING: [], WAIT: [], LET_GO: []}
    for c in g.cards:
        by[c.verdict].append(c)

    print(f"KEEP  ({g.n_keep})  — still last after the cria crop")
    for c in by[KEEP]:
        _print_gate_card(c)
    print(f"\nKEEP UNTIL WEANING  ({g.n_keep_until})  — last today; cria duplicates the blood")
    for c in by[KEEP_UNTIL_WEANING]:
        _print_gate_card(c)
    print(f"\nWAIT  ({g.n_wait})  — one of two living carriers")
    for c in by[WAIT]:
        _print_gate_card(c)

    print(f"\nPAIR LOCKS  ({len(g.pair_locks)})  — do not sell both")
    for p in g.pair_locks[:24]:
        print(f"  {p.founder_name:32s}  {p.a_name}  +  {p.b_name}")
        print(f"      {p.why}")

    print(f"\nLET GO  ({g.n_let_go})  — highest MK first")
    for c in sorted(by[LET_GO], key=lambda x: (-x.mk, x.name)):
        _print_gate_card(c)

    print("\nSUGGESTED SALE  (top LET GO by MK)")
    s = g.suggested_sale
    print(f"  {s.why}")
    if s.names:
        print("  " + ", ".join(s.names))

    print("\nAFTER THE CRIA")
    a = g.after
    print(f"  {a.summary}")
    print(
        f"  last founders {a.n_last_founders_now} → {a.n_last_founders_after}  ·  "
        f"irreplaceable {a.n_irreplaceable_now} → {a.n_irreplaceable_after}  ·  "
        f"Ne {a.ne_now:.1f} → {a.ne_after:.1f}"
    )
    if a.rescued_founders:
        print(f"  duplicated by cria ({len(a.rescued_founders)}):")
        for r in a.rescued_founders[:16]:
            cria = ", ".join(r.cria_names[:2]) or "(share from another pairing)"
            print(f"    {r.founder_name:32s}  was {r.carrier_now}  ·  {cria}")

    csv_path = write_gate_csv(snap, args.out)
    pdf_path = write_gate_pdf(snap, args.out)
    print(f"  csv    {csv_path}")
    print(f"  pdf    {pdf_path}")
    return 0


def cmd_wean(args) -> int:
    snap = _snap(args)
    w = snap.wean
    print(w.summary)
    print()
    print(f"MUST STAY  ({w.n_cover} of {w.n_cria})")
    for c in w.cover:
        print(f"  {c.n_covers:3d} founders  {c.uniqueness_pct:5.1f}%  {c.name}")
        print(f"      {', '.join(c.covers[:6])}")
    print(f"\nSELLABLE WEANLINGS  ({w.n_sellable_cria})")
    for c in w.stay:
        if c.sellable:
            print(f"  F={c.f_pct:5.2f}%  {c.name}")
    print(f"\nPARENT RELEASE  ({w.n_release} may list after weaning)")
    for r in w.releases:
        flag = "MAY LIST" if r.may_sell_after_weaning else "HOLD"
        keep = ", ".join(r.keep_cria[:2]) or "(cover via another pairing)"
        print(f"  {flag:8s}  {r.name:32s}  keep {keep}")
    if w.uncovered:
        print(f"\nNO CRIA BACKUP  ({w.n_uncovered})")
        for name in w.uncovered[:16]:
            print(f"  {name}")
    print(f"\nDISASTER  ({len(w.disaster)} — parent AND their cria both leave)")
    for d in w.disaster[:12]:
        print(f"  {d.parent_name:32s}  {', '.join(d.extinct[:4])}")
    print(f"\nLET GO THIS FALL  ({w.n_this_fall})")
    for s in w.sale_catalog:
        if not s.hold_for_cria:
            print(f"  MK {s.mk_pct:5.2f}%  Ne {s.ne_delta:+.1f}  {s.name}")
    print(f"\nLET GO BUT HOLD FOR A COVERING CRIA  ({w.n_hold_for_cria})")
    for s in w.sale_catalog:
        if s.hold_for_cria:
            print(f"  {s.name:32s}  {', '.join(s.cover_cria[:2])}")
    csv_path = write_wean_csv(snap, args.out)
    ledger = write_wean_pdf(snap, args.out)
    catalog = write_catalog_pdf(snap, args.out)
    print(f"  csv      {csv_path}")
    print(f"  ledger   {ledger}")
    print(f"  catalog  {catalog}")
    return 0


def cmd_next(args) -> int:
    snap = _snap(args)
    n = snap.nxt
    print(n.summary)
    print()
    print("KEEP DAM BAND")
    print(f"  {n.band.summary}")
    if n.band.sold:
        print("  sell: " + ", ".join(n.band.sold[:12]))
    print("\nSHRINK NUCLEUS")
    print(f"  {n.shrink.summary}")
    print(f"\nCOLLISIONS  ({n.n_collisions})  — LET GO sires still booked in years 2–3")
    for c in n.collisions:
        print(f"  {c.sire_name:32s}  Y{'/'.join(str(y) for y in c.years)}  {c.n_bookings}×")
        print(f"      {c.why}")
    print("\nCALENDAR")
    for slot in n.calendar:
        band = "BAND" if slot.path_band else "    "
        shrink = "SHRINK" if slot.path_shrink else "      "
        print(f"  {slot.window:16s}  {band:5s} {shrink:6s}  {slot.sex or '?'}  {slot.name}")
    pdf = write_next_pdf(snap, args.out)
    print(f"  pdf  {pdf}")
    return 0


def cmd_tonight(args) -> int:
    snap = _snap(args)
    for line in tonight_lines(snap):
        print(line)
    csv_path = write_plan_csv(snap, args.out)
    board = write_board_pdf(snap, args.out)
    gate_csv = write_gate_csv(snap, args.out)
    gate_pdf = write_gate_pdf(snap, args.out)
    wean_pdf = write_wean_pdf(snap, args.out)
    nxt_pdf = write_next_pdf(snap, args.out)
    print(f"  csv    {csv_path}")
    print(f"  board  {board}")
    print(f"  gate   {gate_csv}")
    print(f"  keep   {gate_pdf}")
    print(f"  wean   {wean_pdf}")
    print(f"  next   {nxt_pdf}")
    return 0


def cmd_csv(args) -> int:
    snap = _snap(args)
    path = write_plan_csv(snap, args.out)
    rows = path.read_text(encoding="utf-8").strip().splitlines()
    print("wrote", path)
    print(f"  {len(rows) - 1} bookings across {len(snap.rotation) or 1} year(s)")
    return 0


def cmd_board(args) -> int:
    snap = _snap(args)
    path = write_board_pdf(snap, args.out)
    print("wrote", path)
    for plan in snap.rotation or [snap.plan]:
        rescued = [a for a in plan.assignments if a.reason.startswith("rescue:")]
        print(
            f"  year {plan.year}  {len(plan.assignments)} bookings  "
            f"mean F {plan.mean_f*100:.2f}%  rescue {len(rescued)}"
        )
        for a in rescued:
            print(f"    R  {a.dam_name}  ×  {a.sire_name}  F={a.f_pct:.2f}%")
    return 0


def cmd_cards(args) -> int:
    snap = _snap(args)
    path = write_cards_pdf(snap, args.out)
    print("wrote", path)
    print(f"{len(snap.plan.assignments)} cards  ·  year {snap.plan.year}  ·  mean F {snap.plan.mean_f*100:.2f}%")
    rescued = [a for a in snap.plan.assignments if a.reason.startswith("rescue:")]
    for a in rescued:
        print(f"  RESCUE  {a.dam_name}  ×  {a.sire_name}  F={a.f_pct:.2f}%")
    return 0


def cmd_seed_am(args) -> int:
    from .parse import ingest_dir
    from .seed_am import seed_sqlite

    dest = Path(args.dest) if args.dest else args.out / "nucleus.db"
    if dest.name.lower() in {"alpaca_demo.db", "alpaca_data.db"}:
        print("refusing to overwrite", dest, file=sys.stderr)
        return 2
    herd = ingest_dir(args.certs)
    path = seed_sqlite(dest, herd=herd)
    n_owned = sum(1 for a in herd.animals.values() if a.registered)
    print(f"wrote {path}")
    print(f"  registered {n_owned}  ·  graph {len(herd.animals)}  ·  certs {len(herd.sources)}")
    print("Point a Season Book sync at this file. Do not overwrite alpaca_demo.db.")
    return 0


def cmd_book(args) -> int:
    snap = _snap(args)
    write_snapshot(snap, args.out)
    paths = write_all_pdfs(snap, args.out)
    paths.append(write_plan_csv(snap, args.out))
    paths.append(write_gate_csv(snap, args.out))
    paths.append(write_wean_csv(snap, args.out))
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

    p = sub.add_parser("salvage", help="last living carriers of rare founders")
    p.set_defaults(func=cmd_salvage)

    p = sub.add_parser("erode", help="five-year rotation vs barn habit")
    p.set_defaults(func=cmd_erode)

    p = sub.add_parser("gate", help="Keep / Let Go — who can leave, who cannot")
    p.add_argument("animal", nargs="?", default="", help="if they leave: one animal")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("wean", help="which cria must stay if last-carriers leave")
    p.set_defaults(func=cmd_wean)

    p = sub.add_parser("next", help="two sale paths — keep the dam band vs shrink")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("tonight", help="year-1 barn briefing + csv + board")
    p.set_defaults(func=cmd_tonight)

    p = sub.add_parser("csv", help="write SeasonPlan.csv (years 1–3)")
    p.set_defaults(func=cmd_csv)

    p = sub.add_parser("board", help="one-page-per-year barn board PDF")
    p.set_defaults(func=cmd_board)

    p = sub.add_parser("cards", help="barn clipboard cards PDF")
    p.set_defaults(func=cmd_cards)

    p = sub.add_parser("seed-am", help="write a minimal AM-shaped SQLite of the 74")
    p.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="sqlite path (default: --out/nucleus.db). Never alpaca_demo.db.",
    )
    p.set_defaults(func=cmd_seed_am)

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
