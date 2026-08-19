# Season Book

Wright / Malécot genetics on the **74 real AOA certificates** in AlpacaManager. Standalone package — it does not modify AlpacaManager or Hereditas.

The farm can see *what* to book. This desk shows *why*, *which Wright path pushes the number*, *which living animal is the last carrier of a founder*, *what the next generation loses if you keep using the famous stallions*, and *who can actually leave the nucleus this fall*.

## What it is

- **F of a cria** = Malécot coancestry of the parents, expanded by topological pedigree depth (same science as Hereditas). Path lists are barn narration; scoring uses the recurrence.
- **Incomplete pedigrees under-estimate F.** A low F on a thin pedigree is a floor, not an outcross.
- **Color** is the AOA phenotype on the certificate, not an MC1R/ASIP genotype. This does not replace EPDs or lab tests.

On the current certificate set:

| | |
|---|---|
| Graph | 950 animals, 370 founders |
| Nucleus | 74 registered · 48 dams · 26 sires · 0 unsexed |
| Mean F | 1.00% · highest 8.98% (Paloma Picasso = Wonder Woman) |
| Effective size | Ne ≈ 42 · founder genome equivalents ≈ 27 |
| Close kin | 15 BLOCK · 20 CONFIRM among 1,248 dam × sire pairs |
| Gold | Aftershock × Alydar = **25.20% BLOCK** (parent × offspring) |

Snowmass Matrix is legal on every dam and still sits on the bench: capacity fills with lower mean-kinship sires first.

## Commands

```
python -m seasonbook analyze
python -m seasonbook plan
python -m seasonbook audit
python -m seasonbook explain "AFTERSHOCK" --sire "ALYDAR"
python -m seasonbook why "MATRIX"
python -m seasonbook cover
python -m seasonbook kinship
python -m seasonbook horizon
python -m seasonbook salvage
python -m seasonbook erode
python -m seasonbook gate
python -m seasonbook gate "MATRIX"
python -m seasonbook cards
python -m seasonbook tonight
python -m seasonbook csv
python -m seasonbook board
python -m seasonbook seed-am
python -m seasonbook book
python -m seasonbook serve
```

Desk: `http://127.0.0.1:8765/` — keys **1–0** and **G**

Briefing · Atlas · Heatmap · Plan · Mate lab · Audit · Why / cover · Three seasons · Last Blood · Erosion · Keep / Let Go

Printables land in `data/output/`:

- `SeasonBook.pdf`
- `DoNotBook.pdf` (barn wall)
- `FounderCensus.pdf`
- `Rotation.pdf`
- `LastBlood.pdf` (last carriers + 5-year habit cost)
- `BarnCards.pdf` (clipboard: one booking per card)
- `SeasonBoard.pdf` (one page per year, rescue rows gold)
- `KeepLetGo.pdf` (Keep / Let Go, pair-locks, after the cria)
- `TheGate.csv` (one row per registered animal)
- `nucleus.db` (`seed-am` — AM-shaped SQLite of the 74, not the demo herd)
- `snapshot.json`

## The Gate — Keep / Let Go

Last Blood says who is irreplaceable. **The Gate** answers the sale question:

| Verdict | Meaning |
|---|---|
| KEEP | Still the last living carrier *after* the year-1 cria crop. Do not sell. |
| KEEP UNTIL WEANING | Last today. A booked cria is expected to carry that founder at ≥ 3.1%. Keep until the cria is on the ground. |
| WAIT | One of two living carriers. Do not sell both — that is a **pair-lock**. |
| LET GO | Not last, not pair-locked. Ranked by mean kinship: the hottest help Ne when they leave. |

Cria founder share is the mid-parent value (½ dam + ½ sire). Cria kinship is Malécot: θ(cria, X) = ½(θ(sire, X) + θ(dam, X)). Crias are not treated as instant breeders.

`python -m seasonbook gate MATRIX` prints the leave impact: founders that go extinct, who becomes the new last carrier, and the Ne delta.

Certificates are read from `../AlpacaManager/docs/cert_lineage`. Override with `--certs`.

PacaPilot farm tabs (Audit / Census / Last Blood / Horizon / PDFs) read
`data/output/nucleus.db` when the live SQLite has fewer than 40 owned animals
(the Amber demo is 19). Breeding → New still gates against the **live** herd
ids. Override with `SEASONBOOK_NUCLEUS=/path/to/nucleus.db` or `=0` to force live.

## Tests

```
python -m unittest discover -s tests -v
```

Parent × offspring is 0.25 regardless of id order. Aftershock × Alydar is the live gold.

## Verdicts

| | |
|---|---|
| BLOCK | parent × offspring, full sibs, or F ≥ 20% |
| CONFIRM | half-sib / grandparent range, F ≥ 10% |
| PROCEED | below that |

Year-1 assignment: bottleneck dams first, never BLOCK, prefer PROCEED, minimise F then sire mean kinship, capacity 4. Then a **rescue pass** steals one dam from a replaceable sire (2+ bookings) onto each last-carrier stallion that the diversity pass left on the bench. Years 2–3 prefer stallions that have not yet worked.

---

## Implementing this in AlpacaManager

Season Book is **not** a second genetics engine. AlpacaManager already talks to
Hereditas for F, Wright paths, EFI, color, and the GA season plan. Season Book
adds the farm layer Hereditas does not expose: founder census, effective size,
close-kin audit of every registered pair, “why this legal sire sat out”,
three-season rotation, and printable PDFs.

Copy the Hereditas bridge. Do not invent a new transport.

```
React  /hereditas   (add three tabs — do not add a second app)
        │
        ▼
FastAPI
   /api/hereditas/*     already live   →  Hereditas :7842
   /api/seasonbook/*    add this       →  seasonbook (in-process Python)
        │
        SQLite   alpacas + pedigree_ancestors
```

**One number for F.** Mate Lab, Compatibility, and “New breeding” keep calling
`/api/hereditas/explain`. If Season Book and Hereditas ever disagree on
Aftershock × Alydar, the barn will not know whom to trust. Season Book may
*display* F it computed on the certificate graph; it must not overwrite the
Hereditas score stored on a breeding record.

### What to add, file by file

All paths are under `AlpacaManager/`. Do not edit Hereditas.

| File | Change |
|---|---|
| `backend_api/routers/seasonbook.py` | New router. Mirror `routers/hereditas.py`. |
| `backend_api/seasonbook/sync.py` | Build a `HerdGraph` from SQLite, not from markdown. |
| `backend_api/seasonbook/service.py` | Thin wrapper: `build` / `snapshot_dict` / `write_all_pdfs`. |
| `backend_api/main.py` | `app.include_router(seasonbook_router.router)` next to Hereditas. |
| `frontend/src/api/client.ts` | `seasonbookBriefing`, `seasonbookAudit`, `seasonbookCover`, `seasonbookHorizon`, `seasonbookBook`. |
| `frontend/src/pages/Hereditas.tsx` | Three tabs: **Audit**, **Census**, **Horizon**. |
| `frontend/src/pages/` breeding create | On submit, if the pair is BLOCK, refuse. If CONFIRM, require an extra click. |
| `tests/test_seasonbook_bridge.py` | Copy `tests/test_hereditas_bridge.py`. |

Install this package in the AlpacaManager env (editable is fine):

```
pip install -e ../CONSUME_TOKENS_GROK
```

Rename the folder to `seasonbook` first if you want the path to match the
product. The import is `import seasonbook`, not the directory name.

### Identity

Reuse the Hereditas helpers. Do not invent a third id scheme.

| World | Id |
|---|---|
| AlpacaManager PK | `17` |
| Hereditas / API | `am_17` (`am_id` / `parse_am_id` in `backend_api/hereditas/client.py`) |
| AOA registration | `AR:35489856` — already on `pedigree_ancestors.registration_number` |
| Name-only founder | `NM:PERUVIAN HEMINGWAY G171` |

`sync.py` must:

1. Load every row in `alpacas` and `pedigree_ancestors`.
2. Key an animal by `AR:{registration_number}` when that field is present,
   else `am_{pk}` for owned animals, else `NM:{normalized name}`.
3. Apply the same `BY` alias rule Season Book already uses
   (`ALYDAR BY VAL D LSERE` = registered Alydar).
4. Set `registered=True` on owned `alpacas` rows (the breeding nucleus).
5. Set sex from AM `gender` first; only then from sire/dam role.

After a certificate import, the database is the source of truth. The markdown
in `docs/cert_lineage` is the offline fallback for `python -m seasonbook`, not
what the live app should parse.

### Routes to expose

Prefix: `/api/seasonbook`. Same session auth as `/api/hereditas`.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| `POST` | `/sync` | — | `{ animals, registered, dams, sires }` after rebuilding the graph from SQLite |
| `GET` | `/health` | — | `{ ok, built, animals, registered }` |
| `GET` | `/briefing` | — | The `briefing` object in `snapshot.json` (mean F, Ne, fge, BLOCK count, year-1 plan size) |
| `GET` | `/audit` | — | `{ n_block, n_confirm, n_proceed, blocks[], confirms[] }` |
| `GET` | `/census` | — | `{ cards[], founders[], presence[], effective_size, founder_genome_equivalents }` |
| `GET` | `/cover` | `?sire=` optional | Sire coverage + “why they sat out” |
| `GET` | `/horizon` | — | Three-season rotation + projected cria F |
| `GET` | `/plan` | — | Year-1 assignments (capacity default 4) |
| `GET` | `/salvage` | — | Last Blood: irreplaceable animals, last founders, sitting out |
| `GET` | `/erode` | — | Five-year rotation vs barn habit |
| `GET` | `/gate` | `?animal=` optional | Keep / Let Go, pair-locks, after-cria, suggested sale |
| `GET` | `/pair` | `?dam_id=&sire_id=` | BLOCK / CONFIRM / PROCEED for an owned pair |
| `POST` | `/book` | — | Writes the five PDFs; returns their paths or a zip |
| `GET` | `/wall.pdf` | — | `DoNotBook.pdf` (barn wall) |
| `GET` | `/lastblood.pdf` | — | Last Blood printable |
| `GET` | `/gate.pdf` | — | Keep / Let Go printable |

Call `sync` once after login and again after a certificate import. Cache the
`Snapshot` on the process (it is cheap to rebuild: ~1 s on 74 certificates).
Invalidate on alpaca create / pedigree import.

Integer AM ids in, AM ids back out — same as Hereditas:

```python
# request
{ "dam_id": 41, "sire_id": 7 }

# response (always include both)
{ "damAmId": 41, "sireAmId": 7, "dam_name": "...", "sire_name": "...",
  "verdict": "BLOCK", "f_pct": 25.20, "structural": "parent_offspring" }
```

Do **not** add `/api/seasonbook/explain` for the Mate Lab. That path stays
`POST /api/hereditas/explain`.

### UI

Do not create `/seasonbook`. Add tabs on the existing Hereditas page
(`frontend/src/pages/Hereditas.tsx`), next to Mate Lab / Best Sires / Season Plan:

1. **Audit** — the BLOCK list (red) and CONFIRM list (gold). Link each name to
   the alpaca profile. Button: “Download barn wall” → `GET /api/seasonbook/wall.pdf`.
2. **Census** — Ne, founder-genome equivalents, founder share table, presence
   table. Spell out: *presence ≠ gene share*.
3. **Last Blood** — last living carriers, who sits out of year 1, five-year
   habit cost. Button: `GET /api/seasonbook/lastblood.pdf`.
4. **Horizon** — year 1 / 2 / 3 assignments and the projected mean cria F.

On **Breeding → New** (already talks to Hereditas):

- After Hereditas `explain`, also look the pair up in the Season Book audit.
- `BLOCK` → disable Save. Show the structural tag (`parent_offspring`, `full_sib`).
- `CONFIRM` → Save stays enabled, extra checkbox required
  (“half-sib / grandparent range — I still want this booking”).
- `PROCEED` → unchanged.

Grey out a *low* F when `may_underestimate_f` is true. That flag already exists
on Season Book animal cards and on Hereditas completeness objects.

### What each system owns

| Question | Owner |
|---|---|
| What is F of this cria? Which ancestor pushes it? | Hereditas `/explain` |
| Color / EFI / mid-parent EPD | Hereditas |
| GA vs greedy season plan with EPD weights | Hereditas `/optimize` |
| Which of the 1,248 pairs are BLOCK / CONFIRM? | Season Book `/audit` |
| Why is Matrix legal on 48/48 and not in the plan? | Season Book `/cover` |
| Who owns this herd’s genome? What is Ne? | Season Book `/census` |
| Same dams, different sires, years 2 and 3 | Season Book `/horizon` |
| Who can leave this fall? Who is pair-locked? | Season Book `/gate` |
| Paper on the barn wall | Season Book `/wall.pdf` |

### Implementation order

Do these in order. Each step is shippable on its own.

1. **Sync only.** `POST /api/seasonbook/sync` + `GET /health`. Prove the
   SQLite graph has 74 registered animals, 0 unsexed, and Aftershock’s sire
   is Alydar (`AR:35489856`). Gold: Aftershock × Alydar is structural
   `parent_offspring`. If this fails, stop — the rest is noise.
2. **Audit + wall PDF.** Router + Audit tab + download. No planner yet.
3. **Census.** Ne and founder table. One screen.
4. **Cover + Horizon.** “Why Matrix sat out” and the three-year rotation.
5. **Breeding gate.** BLOCK refuses save; CONFIRM asks once.
6. **Wire printables** into the existing Printables page
   (`backend_api/routers/printables.py`) so the PDFs live next to the other
   farm paper.

### Checks before you call it done

- `python -m unittest discover -s tests -v` still green in this repo
  (Aftershock × Alydar = 25.20% BLOCK).
- `POST /api/seasonbook/sync` on the demo DB does not raise, and
  `registered` matches the owned-herd count.
- Mate Lab still hits `/api/hereditas/explain`, not Season Book.
- Saving Aftershock × Alydar as a breeding is refused.
- Matrix appears in `/cover` as “100% legal; lost on capacity to lower-MK sires.”
- `/wall.pdf` lists the same 15 BLOCK rows as `/audit`.
- A low F with `may_underestimate_f` is not shown as an outcross.

### What not to do

- Do not parse `docs/cert_lineage` from the live app. That folder is the
  offline desk’s input. The live app reads SQLite after certificate import.
- Do not start a second Node or Python HTTP server for production. Import
  `seasonbook` in-process from FastAPI, the way the rest of the backend
  already imports `clean_database`. `:8765` stays a local command-center
  (`python -m seasonbook serve`) for people who are not running PacaPilot.
- Do not replace Hereditas `/optimize` with Season Book’s greedy assigner.
  Hereditas owns EPD/EFI-weighted plans. Season Book’s assigner is the
  diversity-first booking list (low F, low MK, capacity 4).
- Do not hide BLOCK cells on the heatmap. Red stays visible.
