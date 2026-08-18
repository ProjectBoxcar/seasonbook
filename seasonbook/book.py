"""Printable PDFs: Season Book, Do-Not-Book wall, founder census, three-season rotation.

Minimal PDF 1.4 writer. Helvetica only, no third-party dependency.
"""

from __future__ import annotations

from pathlib import Path

from .pipeline import DEFAULT_OUT, Snapshot


def _esc(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", " ")
    )


class _Pdf:
    def __init__(self, title: str) -> None:
        self.title = title
        self.pages: list[list[bytes]] = []
        self._page: list[bytes] = []
        self.w = 612
        self.h = 792

    def new_page(self) -> None:
        if self._page:
            self.pages.append(self._page)
        self._page = []
        # cream page fill
        self._page.append(b"0.96 0.94 0.88 rg 0 0 612 792 re f\n")

    def text(self, x: float, y: float, size: float, s: str, r=0.12, g=0.10, b=0.08) -> None:
        content = _esc(s)
        self._page.append(
            f"{r:.3f} {g:.3f} {b:.3f} rg BT /F1 {size:.1f} Tf {x:.1f} {y:.1f} Td ({content}) Tj ET\n".encode(
                "latin-1", "replace"
            )
        )

    def rule(self, x: float, y: float, w: float, thick: float = 0.6, r=0.55, g=0.42, b=0.18) -> None:
        self._page.append(
            f"{r:.3f} {g:.3f} {b:.3f} RG {thick:.2f} w {x:.1f} {y:.1f} m {x+w:.1f} {y:.1f} l S\n".encode()
        )

    def box(self, x, y, w, h, r=0.90, g=0.22, b=0.18) -> None:
        self._page.append(
            f"{r:.3f} {g:.3f} {b:.3f} rg {x:.1f} {y:.1f} {w:.1f} {h:.1f} re f\n".encode()
        )

    def finish_page(self) -> None:
        if self._page:
            self.pages.append(self._page)
            self._page = []

    def save(self, path: Path) -> None:
        self.finish_page()
        objects: list[bytes] = []

        def add(payload: bytes) -> int:
            objects.append(payload)
            return len(objects)

        font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        page_ids: list[int] = []
        content_ids: list[int] = []
        for page in self.pages:
            stream = b"".join(page)
            content_ids.append(
                add(
                    f"<< /Length {len(stream)} >>\nstream\n".encode()
                    + stream
                    + b"endstream"
                )
            )
        pages_id = len(objects) + len(self.pages) + 1  # reserved, fill later
        for i, cid in enumerate(content_ids):
            page_ids.append(
                add(
                    (
                        f"<< /Type /Page /Parent {pages_id} 0 R "
                        f"/MediaBox [0 0 612 792] /Contents {cid} 0 R "
                        f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
                    ).encode()
                )
            )
        kids = " ".join(f"{pid} 0 R" for pid in page_ids)
        # pages object must sit at pages_id — we appended pages after contents,
        # so insert by appending now and... wait, we computed pages_id assuming
        # we add pages then the pages node. page objects were just added, next is pages.
        actual_pages = add(
            f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
        )
        # If reservation drifted, rewrite parent refs. Safer: write pages first next time.
        # Here actual_pages should equal pages_id.
        if actual_pages != pages_id:
            # rewrite page objects' Parent
            for pid in page_ids:
                objects[pid - 1] = objects[pid - 1].replace(
                    f"/Parent {pages_id} 0 R".encode(),
                    f"/Parent {actual_pages} 0 R".encode(),
                )
            pages_id = actual_pages
        info_id = add(f"<< /Title ({_esc(self.title)}) /Creator (Season Book) >>".encode())
        cat_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for i, obj in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode()
            out += obj
            out += b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objects)+1}\n".encode()
        out += b"0000000000 65535 f \n"
        for off in offsets[1:]:
            out += f"{off:010d} 00000 n \n".encode()
        out += (
            f"trailer\n<< /Size {len(objects)+1} /Root {cat_id} 0 R /Info {info_id} 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(out))


def _header(pdf: _Pdf, eyebrow: str, title: str, sub: str) -> int:
    pdf.box(0, 752, 612, 40, 0.18, 0.14, 0.10)
    pdf.text(36, 768, 9, eyebrow.upper(), 0.82, 0.68, 0.32)
    pdf.text(36, 730, 18, title, 0.18, 0.14, 0.10)
    pdf.text(36, 712, 9, sub, 0.35, 0.30, 0.22)
    pdf.rule(36, 704, 540, 1.0)
    return 688


def write_season_book(snap: Snapshot, out_dir: Path | None = None) -> Path:
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    b = snap.briefing()
    pdf = _Pdf("Season Book")
    pdf.new_page()
    y = _header(
        pdf,
        "Season Book  ·  Wright / Malécot",
        "Breeding season on the real certificates",
        f"{b['certificates']} AOA certificates  ·  {b['animals']} animals  ·  "
        f"{b['dams']} dams × {b['sires']} sires  ·  built {b['built']}",
    )
    stats = [
        (f"{b['mean_f_pct']:.2f}%", "Mean F of registered"),
        (f"{b['max_f_pct']:.2f}%", f"Highest F  ·  {b['max_f_name'][:28]}"),
        (f"{b['effective_size']:.1f}", "Effective size (Ne)"),
        (f"{b['founder_genome_equivalents']:.1f}", "Founder genome equiv."),
        (f"{b['blocks']}", "BLOCK pairings"),
        (f"{b['plan_n']}", f"Year-1 bookings  ·  F {b['plan_mean_f_pct']:.2f}%"),
    ]
    x = 36
    for val, label in stats:
        pdf.box(x, y - 48, 88, 56, 0.93, 0.90, 0.82)
        pdf.text(x + 6, y - 8, 14, val, 0.18, 0.14, 0.10)
        pdf.text(x + 6, y - 36, 7, label[:22], 0.38, 0.32, 0.22)
        x += 94
    y -= 80
    pdf.text(36, y, 11, "What this number is, and is not", 0.18, 0.14, 0.10)
    y -= 16
    notes = [
        "F of a cria is the Malecot coancestry of its parents. Path lists are narration; scoring uses the recurrence.",
        "Missing ancestors can only push F up. A low F on a thin pedigree is a floor, not an outcross.",
        "Color on these certificates is AOA phenotype, not MC1R/ASIP genotype. This does not replace EPDs or lab tests.",
        "BLOCK is parent x offspring, full sibs, or F >= 20%. CONFIRM is half-sib / grandparent range (F >= 10%).",
        f"The registered nucleus behaves like ~{b['effective_size']:.0f} unrelated animals, not {b['registered']}.",
    ]
    for line in notes:
        pdf.text(36, y, 8, line[:108], 0.25, 0.22, 0.16)
        y -= 12

    y -= 8
    rescued = sum(1 for a in snap.plan.assignments if a.reason.startswith("rescue:"))
    pdf.text(
        36,
        y,
        11,
        f"Year-1 plan  (capacity 4, then {rescued} last-carrier rescue swap(s))",
        0.18,
        0.14,
        0.10,
    )
    y -= 16
    pdf.text(36, y, 8, "DAM", 0.45, 0.38, 0.22)
    pdf.text(250, y, 8, "SIRE", 0.45, 0.38, 0.22)
    pdf.text(430, y, 8, "F", 0.45, 0.38, 0.22)
    pdf.text(470, y, 8, "WHY", 0.45, 0.38, 0.22)
    y -= 4
    pdf.rule(36, y, 540, 0.4)
    y -= 12
    for a in snap.plan.assignments:
        if y < 48:
            pdf.new_page()
            y = _header(pdf, "Season Book", "Year-1 plan (continued)", "")
        pdf.text(36, y, 8, a.dam_name[:38])
        pdf.text(250, y, 8, a.sire_name[:32])
        pdf.text(460, y, 8, f"{a.f_pct:.2f}%")
        pdf.text(510, y, 8, a.verdict, 0.35, 0.30, 0.22)
        y -= 11

    # Audit chapter
    pdf.new_page()
    y = _header(
        pdf,
        "Close-kin audit",
        f"{snap.audit.n_block} BLOCK  ·  {snap.audit.n_confirm} CONFIRM",
        f"{snap.audit.n_block + snap.audit.n_confirm + snap.audit.n_proceed} dam x sire pairs on the registered nucleus",
    )
    pdf.text(36, y, 11, "Do not book these", 0.55, 0.16, 0.12)
    y -= 16
    for p in snap.audit.blocks:
        if y < 48:
            pdf.new_page()
            y = _header(pdf, "Close-kin audit", "BLOCK (continued)", "")
        tag = (p.structural or "close kin").replace("_", " ")
        pdf.text(36, y, 9, f"{p.dam_name}  x  {p.sire_name}", 0.45, 0.12, 0.10)
        pdf.text(400, y, 9, f"F={p.f_pct:.2f}%  {tag}")
        y -= 12

    y -= 10
    pdf.text(36, y, 11, "Confirm before you book", 0.50, 0.38, 0.10)
    y -= 16
    for p in snap.audit.confirms:
        if y < 48:
            pdf.new_page()
            y = _header(pdf, "Close-kin audit", "CONFIRM (continued)", "")
        pdf.text(36, y, 8, f"{p.dam_name}  x  {p.sire_name}")
        extra = f" via {p.top_ancestor}" if p.top_ancestor else ""
        pdf.text(400, y, 8, f"F={p.f_pct:.2f}%{extra}")
        y -= 11

    path = out_dir / "SeasonBook.pdf"
    pdf.save(path)
    return path


def write_wall(snap: Snapshot, out_dir: Path | None = None) -> Path:
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    pdf = _Pdf("Do Not Book")
    pdf.new_page()
    pdf.box(0, 0, 612, 792, 0.17, 0.11, 0.09)
    pdf.text(36, 750, 11, "BARN WALL  ·  DO NOT BOOK", 0.82, 0.68, 0.32)
    pdf.text(36, 720, 22, f"{snap.audit.n_block} pairings are closed this season", 0.96, 0.93, 0.88)
    pdf.text(
        36,
        700,
        9,
        "Parent x offspring, full sibs, or F >= 20%. Tape this next to the breeding chart.",
        0.82,
        0.74,
        0.62,
    )
    y = 670
    for p in snap.audit.blocks:
        if y < 60:
            pdf.new_page()
            pdf.box(0, 0, 612, 792, 0.17, 0.11, 0.09)
            y = 740
        pdf.box(36, y - 10, 540, 30, 0.28, 0.14, 0.12)
        tag = (p.structural or "close kin").replace("_", " ").upper()
        pair = f"{p.dam_name}  x  {p.sire_name}"
        pdf.text(44, y + 4, 9, pair[:62], 0.96, 0.93, 0.88)
        pdf.text(44, y - 8, 8, f"{p.f_pct:.2f}%   {tag}", 0.90, 0.55, 0.40)
        y -= 36
    path = out_dir / "DoNotBook.pdf"
    pdf.save(path)
    return path


def write_census_pdf(snap: Snapshot, out_dir: Path | None = None) -> Path:
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    b = snap.briefing()
    pdf = _Pdf("Founder Census")
    pdf.new_page()
    y = _header(
        pdf,
        "Founder census",
        "Who actually owns this herd's genome",
        f"Ne = {b['effective_size']:.1f}   ·   founder genome equivalents = {b['founder_genome_equivalents']:.2f}   ·   "
        f"{b['founders']} pedigree founders",
    )
    pdf.text(36, y, 10, "Expected Mendelian contribution (registered nucleus)")
    y -= 16
    pdf.text(36, y, 8, "FOUNDER", 0.45, 0.38, 0.22)
    pdf.text(360, y, 8, "SHARE", 0.45, 0.38, 0.22)
    pdf.text(430, y, 8, "IN PEDIGREES", 0.45, 0.38, 0.22)
    y -= 12
    for f in snap.census.founders[:28]:
        if f.contribution < 0.008:
            continue
        pdf.text(36, y, 8, f.name[:48])
        pdf.text(360, y, 8, f"{f.contribution*100:.2f}%")
        pdf.text(430, y, 8, f"{f.presence}/{b['registered']}  ({f.presence_pct:.0f}%)")
        y -= 11
    y -= 16
    pdf.text(36, y, 10, "Most present ancestors (a name in many trees is not the same as gene share)")
    y -= 14
    for f in snap.census.presence[:12]:
        pdf.text(36, y, 8, f"{f.name[:48]}")
        pdf.text(430, y, 8, f"{f.presence}/{b['registered']} pedigrees")
        y -= 11
    path = out_dir / "FounderCensus.pdf"
    pdf.save(path)
    return path


def write_rotation_pdf(snap: Snapshot, out_dir: Path | None = None) -> Path:
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    pdf = _Pdf("Three-season rotation")
    pdf.new_page()
    y = _header(
        pdf,
        "Three-season rotation",
        "Same dams, fresher sires each year",
        "Year 2 and 3 prefer stallions that have not yet worked. Capacity stays 4.",
    )
    for plan in snap.rotation:
        if y < 120:
            pdf.new_page()
            y = _header(pdf, "Three-season rotation", "Continued", "")
        pdf.text(36, y, 12, f"Year {plan.year}   ·   {len(plan.assignments)} bookings   ·   mean F {plan.mean_f*100:.2f}%")
        y -= 14
        used = ", ".join(f"{n}×{c}" for n, c in sorted(plan.used_sires.items()))
        pdf.text(36, y, 8, used[:110], 0.35, 0.30, 0.22)
        y -= 16
        for a in plan.assignments:
            if y < 48:
                pdf.new_page()
                y = _header(pdf, "Three-season rotation", f"Year {plan.year} continued", "")
            pdf.text(36, y, 8, a.dam_name[:34])
            pdf.text(280, y, 8, a.sire_name[:30])
            pdf.text(500, y, 8, f"{a.f_pct:.2f}%")
            y -= 11
        y -= 12
    path = out_dir / "Rotation.pdf"
    pdf.save(path)
    return path


def write_last_blood_pdf(snap: Snapshot, out_dir: Path | None = None) -> Path:
    """Barn wall: animals that uniquely carry a founder, and the 5-year habit cost."""
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    lb = snap.last_blood
    e = snap.erosion
    pdf = _Pdf("Last Blood")
    pdf.new_page()
    y = _header(
        pdf,
        "Last Blood  ·  conservation genetics of the nucleus",
        "If these animals sit out, this blood leaves the herd",
        f"{lb.n_irreplaceable} irreplaceable  ·  {lb.n_last_founders} last founders  ·  "
        f"{len(lb.sitting_out)} sitting out of year 1  ·  built {snap.built}",
    )
    pdf.text(36, y, 9, "A founder is last when only one registered animal still carries ≥ 3.1% of it.", 0.35, 0.30, 0.22)
    y -= 14
    pdf.text(36, y, 11, "Sitting out this season", 0.55, 0.16, 0.12)
    y -= 16
    if not lb.sitting_out:
        pdf.text(36, y, 9, "Every last carrier is already in the year-1 plan.")
        y -= 14
    for c in lb.sitting_out:
        if y < 56:
            pdf.new_page()
            y = _header(pdf, "Last Blood", "Sitting out (continued)", "")
        pdf.text(36, y, 9, f"{c.name}  ({c.sex or '?'})", 0.45, 0.12, 0.10)
        pdf.text(360, y, 8, f"{c.uniqueness_pct:.1f}% unique  MK {c.mk_pct:.2f}%")
        y -= 11
        pdf.text(48, y, 8, c.why[:100], 0.30, 0.26, 0.20)
        y -= 13

    if lb.rescue:
        y -= 8
        pdf.text(36, y, 11, "Rescue bookings (one legal dam, lowest F)", 0.18, 0.14, 0.10)
        y -= 16
        for r in lb.rescue:
            if y < 56:
                pdf.new_page()
                y = _header(pdf, "Last Blood", "Rescue bookings (continued)", "")
            pdf.text(36, y, 9, f"{r['sire_name']}  x  {r['dam_name']}  F={r['f_pct']:.2f}%")
            y -= 11
            pdf.text(48, y, 8, str(r["why"])[:100], 0.30, 0.26, 0.20)
            y -= 13

    y -= 6
    pdf.text(36, y, 11, "Every last carrier", 0.18, 0.14, 0.10)
    y -= 16
    for c in lb.cards:
        if not c.irreplaceable:
            continue
        if y < 48:
            pdf.new_page()
            y = _header(pdf, "Last Blood", "Irreplaceable (continued)", "")
        flag = "BOOKED" if c.in_year1_plan else "SITS OUT"
        pdf.text(36, y, 8, c.name[:34])
        pdf.text(260, y, 8, c.sex or "?")
        pdf.text(290, y, 8, f"{c.uniqueness_pct:.1f}%")
        pdf.text(340, y, 8, flag, 0.55, 0.16, 0.12 if not c.in_year1_plan else 0.22)
        pdf.text(410, y, 8, ", ".join(c.last_of[:3])[:40], 0.30, 0.26, 0.20)
        y -= 11

    pdf.new_page()
    y = _header(
        pdf,
        "Five-year counterfactual",
        "Rotation vs barn habit",
        e.summary[:120],
    )
    pdf.text(36, y, 9, "Habit = hottest legal sire still under capacity. That is Matrix / Alydar / Smokin Waves.", 0.35, 0.30, 0.22)
    y -= 18
    pdf.text(36, y, 8, "YEAR")
    pdf.text(90, y, 8, "ROT F")
    pdf.text(150, y, 8, "HABIT F")
    pdf.text(230, y, 8, "ROT FOUNDERS")
    pdf.text(340, y, 8, "HABIT FOUNDERS")
    y -= 4
    pdf.rule(36, y, 540, 0.4)
    y -= 14
    for r, h in zip(e.rotation, e.habit):
        pdf.text(36, y, 10, str(r.year))
        pdf.text(90, y, 10, f"{r.mean_f_pct:.2f}%")
        pdf.text(150, y, 10, f"{h.mean_f_pct:.2f}%")
        pdf.text(230, y, 10, str(r.n_founders))
        pdf.text(340, y, 10, str(h.n_founders))
        y -= 14

    y -= 10
    pdf.text(36, y, 11, "Founders the rotation keeps and habit drops", 0.18, 0.14, 0.10)
    y -= 16
    if not e.saved_by_rotation:
        pdf.text(36, y, 9, "None at the 3.1% threshold — habit still concentrates the top blood.")
        y -= 14
    for row in e.saved_by_rotation[:28]:
        if y < 48:
            pdf.new_page()
            y = _header(pdf, "Last Blood", "Founders habit drops (continued)", "")
        pdf.text(36, y, 8, row.founder_name[:34])
        pdf.text(280, y, 8, f"nucleus {row.nucleus_share_pct:.2f}%")
        pdf.text(390, y, 8, f"rot {row.rotation_share_pct:.2f}%")
        pdf.text(480, y, 8, f"habit {row.habit_share_pct:.2f}%")
        y -= 11

    path = out_dir / "LastBlood.pdf"
    pdf.save(path)
    return path


def write_board_pdf(snap: Snapshot, out_dir: Path | None = None) -> Path:
    """One-page-per-year barn board. Rescue rows stay visible."""
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    pdf = _Pdf("Season board")
    plans = list(snap.rotation) or [snap.plan]
    for plan in plans:
        pdf.new_page()
        rescued = sum(1 for a in plan.assignments if a.reason.startswith("rescue:"))
        y = _header(
            pdf,
            "Season board  ·  pin this up",
            f"Year {plan.year}  ·  {len(plan.assignments)} bookings",
            f"mean F {plan.mean_f * 100:.2f}%  ·  {rescued} last-carrier rescue  ·  "
            f"{len(plan.used_sires)} sires  ·  {snap.built}",
        )
        pdf.text(36, y, 8, "R = rescue (last living carrier). Do not skip the gold rows.", 0.45, 0.32, 0.16)
        y -= 16
        pdf.text(36, y, 8, "DAM")
        pdf.text(250, y, 8, "SIRE")
        pdf.text(460, y, 8, "F")
        pdf.text(510, y, 8, "")
        y -= 4
        pdf.rule(36, y, 540, 0.4)
        y -= 12
        for a in plan.assignments:
            if y < 40:
                pdf.new_page()
                y = _header(pdf, "Season board", f"Year {plan.year} continued", "")
            rescue = a.reason.startswith("rescue:")
            if rescue:
                pdf.box(36, y - 3, 540, 12, 0.93, 0.84, 0.62)
                pdf.text(36, y, 8, a.dam_name[:34], 0.40, 0.18, 0.06)
                pdf.text(250, y, 8, a.sire_name[:32], 0.40, 0.18, 0.06)
                pdf.text(460, y, 8, f"{a.f_pct:.2f}%", 0.40, 0.18, 0.06)
                pdf.text(510, y, 8, "R", 0.55, 0.16, 0.12)
            else:
                pdf.text(36, y, 8, a.dam_name[:34])
                pdf.text(250, y, 8, a.sire_name[:32])
                pdf.text(460, y, 8, f"{a.f_pct:.2f}%")
            y -= 11
        y -= 10
        pdf.text(36, y, 8, "Sires: " + ", ".join(
            f"{n}×{c}" for n, c in sorted(plan.used_sires.items(), key=lambda kv: (-kv[1], kv[0]))
        )[:110], 0.35, 0.30, 0.22)
    path = out_dir / "SeasonBoard.pdf"
    pdf.save(path)
    return path


def write_cards_pdf(snap: Snapshot, out_dir: Path | None = None) -> Path:
    """Clipboard cards — one booking per card, 6 to a letter page."""
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    pdf = _Pdf("Barn cards")
    slots = [
        (36, 540),
        (318, 540),
        (36, 300),
        (318, 300),
        (36, 60),
        (318, 60),
    ]
    w, h = 258, 228
    assignments = list(snap.plan.assignments)
    if not assignments:
        pdf.new_page()
        _header(pdf, "Barn cards", "No year-1 bookings", "")
    for i, a in enumerate(assignments):
        if i % 6 == 0:
            pdf.new_page()
            pdf.text(36, 776, 8, f"Year {a.year}  ·  barn cards  ·  {snap.built}", 0.45, 0.38, 0.22)
        x, y = slots[i % 6]
        rescue = a.reason.startswith("rescue:")
        if rescue:
            pdf.box(x, y, 6, h, 0.72, 0.42, 0.12)
        else:
            pdf.box(x, y, 6, h, 0.18, 0.42, 0.28)
        pdf.box(x + 6, y, w - 6, h, 0.98, 0.96, 0.90)
        pdf.text(x + 16, y + h - 22, 8, "DAM", 0.45, 0.38, 0.22)
        pdf.text(x + 16, y + h - 40, 12, a.dam_name[:28], 0.18, 0.14, 0.10)
        pdf.text(x + 16, y + h - 58, 8, "SIRE", 0.45, 0.38, 0.22)
        pdf.text(x + 16, y + h - 76, 12, a.sire_name[:28], 0.18, 0.14, 0.10)
        tag = "RESCUE" if rescue else a.verdict
        pdf.text(x + 16, y + h - 100, 14, f"F = {a.f_pct:.2f}%", 0.18, 0.14, 0.10)
        pdf.text(x + 150, y + h - 100, 10, tag, 0.55, 0.16, 0.12 if rescue else 0.22)
        pair = next(
            (
                p
                for p in snap.pairs
                if p.dam_id == a.dam_id and p.sire_id == a.sire_id
            ),
            None,
        )
        if pair and pair.top_ancestor and pair.F >= 0.01:
            pdf.text(
                x + 16,
                y + 108,
                8,
                f"Wright: {pair.top_ancestor[:28]} ({pair.top_contrib_pct:.0f}% of F)",
                0.35,
                0.22,
                0.12,
            )
        reason = a.reason or ""
        for n, start in enumerate(range(0, min(len(reason), 180), 42)):
            pdf.text(x + 16, y + 88 - n * 12, 8, reason[start : start + 42], 0.30, 0.26, 0.20)
        pdf.text(x + 16, y + 16, 8, f"card {i + 1} / {len(assignments)}", 0.45, 0.38, 0.22)
    path = out_dir / "BarnCards.pdf"
    pdf.save(path)
    return path


def write_all_pdfs(snap: Snapshot, out_dir: Path | None = None) -> list[Path]:
    return [
        write_season_book(snap, out_dir),
        write_wall(snap, out_dir),
        write_census_pdf(snap, out_dir),
        write_rotation_pdf(snap, out_dir),
        write_last_blood_pdf(snap, out_dir),
        write_cards_pdf(snap, out_dir),
        write_board_pdf(snap, out_dir),
    ]
