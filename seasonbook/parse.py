"""Parse AOA lineage markdown into a unified pedigree graph.

Identity is registration number first, cleaned name second. The graph
decides sex when an animal appears as sire or dam; certificate titles
are not trusted for sex.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .subjects import lookup_registered
from .wright import PedigreeNode

LINE_RE = re.compile(
    r"^(?P<indent>\s*)- \*\*(?P<role>Sire|Dam)\*\*\s+(?P<rest>.+?)\s*$"
)
TREE_RE = re.compile(
    r"[├└│\s─]*[♂♀]?\s*(?P<sex>[♂♀])\s+(?P<body>.+?)\s*$"
)
AR_TICK = re.compile(r"`(\d{4,})`")
AR_PAREN = re.compile(r"\((\d{4,})\)")
HUACAVA = re.compile(r"Huaca[yv]a\s+(\d{4,})", re.I)
HUACAVA_TAIL = re.compile(
    r"\s*Huaca[yv]a\s+\S+.*$",
    re.I,
)
COUNTRY_TAIL = re.compile(
    r"\s*[-–—]\s*(United States|Peru|Australia|Canada|Chile|Bolivia).*$",
    re.I,
)
COLOR_SPLIT = re.compile(r"\s+[—–-]\s+([A-Z]{1,4}(?:\s+[A-Z]{1,4}){0,4})\s*$")
FARM_CODE = re.compile(r"\s*\([A-Z]{1,4}\d{2,4}\)(?:\s+and\b.*)?\s*$", re.I)
OWNER_CUT = re.compile(
    r"\s+(?:AND/OR|and/or|and)\s+[A-Z].*$"
)

# Color codes that appear after an em-dash on lineage lines.
COLOR_TOKEN = re.compile(
    r"^(?:[A-Z]{1,3}|LB|LF|MB|MF|TB|TF|DB|DF|BB|BG|WH|MSG|DSG|DRG|LRG|MRG|SB)$"
)


@dataclass
class RawAnimal:
    key: str
    name: str
    ar: str | None = None
    sire_key: str | None = None
    dam_key: str | None = None
    sex: str | None = None
    color: str | None = None
    registered: bool = False
    source: str = ""


@dataclass
class HerdGraph:
    animals: dict[str, RawAnimal] = field(default_factory=dict)
    registered_ids: list[str] = field(default_factory=list)
    name_index: dict[str, str] = field(default_factory=dict)
    ar_index: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    def to_pedigree(self) -> dict[str, PedigreeNode]:
        return {
            aid: PedigreeNode(
                id=aid,
                sire_id=a.sire_key,
                dam_id=a.dam_key,
                name=a.name,
            )
            for aid, a in self.animals.items()
        }


def normalize_name(raw: str) -> str:
    s = (raw or "").strip()
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u2032", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = HUACAVA_TAIL.sub("", s)
    s = COUNTRY_TAIL.sub("", s)
    s = s.replace("*", "")
    s = re.sub(r"^[\s|.\-=]+", "", s)
    s = re.sub(r"[\s|.\-=]+$", "", s)
    # OCR leftovers that leaked into names
    s = s.replace("= ", " ").replace(">", " ")
    s = re.sub(r"\s+", " ", s).strip()
    # Stylized XXX / XXxX / XXXX on Conopa-class names collapse to XXX
    s = re.sub(r"\bXXX+\b", "XXX", s, flags=re.I)
    s = re.sub(r"\bXXxX\b", "XXX", s, flags=re.I)
    return s


def name_key(name: str) -> str:
    s = normalize_name(name).upper()
    s = s.replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def alias_name_keys(name: str) -> list[str]:
    """'ALYDAR BY VAL D LSERE' must collide with registered 'ALYDAR'."""
    key = name_key(name)
    aliases = [key]
    if " BY " in key:
        aliases.append(key.split(" BY ", 1)[0].strip())
    # drop empty / too-short prefixes (avoid 'RR' matching everything)
    return [a for a in aliases if len(a) >= 8]


def is_junk_name(name: str) -> bool:
    """OCR crumbs that are not animals. Keep short real names that have an AR."""
    raw = (name or "").strip()
    if not raw or any(ch in raw for ch in "@\\"):
        return True
    key = name_key(raw)
    if len(key) < 3:
        return True
    if not re.search(r"[A-Z]{3,}", key):
        return True
    meaningful = [t for t in key.split() if t not in {"AND", "THE", "OF", "BY", "A", "AN"}]
    if not meaningful:
        return True
    letters = "".join(meaningful)
    if len(letters) < 3:
        return True
    short = sum(1 for t in meaningful if len(t) <= 2)
    if short == len(meaningful) and len(letters) < 10:
        return True
    return False


def extract_ar(text: str) -> str | None:
    for rx in (AR_TICK, HUACAVA, AR_PAREN):
        m = rx.search(text)
        if m:
            return m.group(1)
    return None


def extract_color(text: str) -> str | None:
    m = COLOR_SPLIT.search(text)
    if not m:
        return None
    tokens = m.group(1).split()
    if tokens and all(COLOR_TOKEN.match(t) for t in tokens):
        return " ".join(tokens)
    return None


def strip_meta(text: str) -> str:
    s = AR_TICK.sub("", text)
    s = HUACAVA_TAIL.sub("", s)
    s = COLOR_SPLIT.sub("", s)
    s = AR_PAREN.sub("", s)
    return normalize_name(s)


def _split_rest(rest: str) -> tuple[str, str | None, str | None]:
    ar = extract_ar(rest)
    color = extract_color(rest)
    name = strip_meta(rest)
    return name, ar, color


def _subject_from_title(title: str) -> str:
    s = title.strip()
    if s.startswith("#"):
        s = s[1:].strip()
    s = FARM_CODE.sub("", s)
    s = OWNER_CUT.sub("", s)
    # Title-case farm tails ("Fulcrum Farms", "Marc Milligan")
    m = re.search(r"\s+([A-Z][a-z].*)$", s)
    if m and not re.search(r"\bBY\b", m.group(1).upper()):
        s = s[: m.start()].strip()
    return normalize_name(s)


def parse_certificate(text: str, filename: str = "") -> tuple[RawAnimal, list[RawAnimal]]:
    lines = text.splitlines()
    title = next((ln for ln in lines if ln.startswith("# ")), "")
    looked = lookup_registered(filename) if filename else None
    if looked:
        subject_name, subject_sex = looked
    else:
        subject_name = _subject_from_title(title)
        subject_sex = None

    lineage: list[tuple[int, str, str, str | None, str | None]] = []
    tree_sex: dict[str, str] = {}

    in_tree = False
    for ln in lines:
        if ln.strip().startswith("```"):
            in_tree = not in_tree
            continue
        if in_tree:
            tm = TREE_RE.search(ln)
            if tm:
                body = tm.group("body")
                sex = "M" if tm.group("sex") == "♂" else "F"
                nm, ar, _ = _split_rest(body)
                if ar:
                    tree_sex[f"AR:{ar}"] = sex
                tree_sex[f"NM:{name_key(nm)}"] = sex
            continue
        lm = LINE_RE.match(ln.rstrip())
        if not lm:
            continue
        indent = len(lm.group("indent").replace("\t", "  "))
        role = lm.group("role")
        name, ar, color = _split_rest(lm.group("rest"))
        if not ar and is_junk_name(name):
            continue
        if not name and not ar:
            continue
        lineage.append((indent, role, name, ar, color))

    # Walk lineage as a stack of (indent, key) to attach parents.
    nodes: dict[str, RawAnimal] = {}

    def ensure(name: str, ar: str | None, color: str | None, sex: str | None) -> str:
        key = f"AR:{ar}" if ar else f"NM:{name_key(name)}"
        if key not in nodes:
            nodes[key] = RawAnimal(key=key, name=normalize_name(name), ar=ar, color=color, sex=sex)
        else:
            if color and not nodes[key].color:
                nodes[key].color = color
            if ar and not nodes[key].ar:
                nodes[key].ar = ar
            if sex and not nodes[key].sex:
                nodes[key].sex = sex
            # Prefer the longer clean name
            if len(normalize_name(name)) > len(nodes[key].name):
                nodes[key].name = normalize_name(name)
        # apply tree sex
        if nodes[key].sex is None:
            nodes[key].sex = tree_sex.get(key) or tree_sex.get(f"NM:{name_key(name)}")
        return key

    subject_key = ensure(subject_name, None, None, subject_sex)
    subject = nodes[subject_key]
    subject.registered = True
    subject.source = filename
    if subject_sex:
        subject.sex = subject_sex

    stack: list[tuple[int, str, str]] = [(-1, subject_key, "subject")]
    for indent, role, name, ar, color in lineage:
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent_key = stack[-1][1] if stack else subject_key
        sex = "M" if role == "Sire" else "F"
        child_key = ensure(name, ar, color, sex)
        parent = nodes[parent_key]
        if role == "Sire":
            parent.sire_key = child_key
        else:
            parent.dam_key = child_key
        stack.append((indent, child_key, role))

    return subject, list(nodes.values())


def ingest_dir(cert_dir: Path) -> HerdGraph:
    herd = HerdGraph()
    files = sorted(Path(cert_dir).glob("*.md"))
    if not files:
        raise FileNotFoundError(f"No certificates in {cert_dir}")

    pending: list[RawAnimal] = []
    subjects: list[RawAnimal] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        subject, nodes = parse_certificate(text, path.name)
        subjects.append(subject)
        pending.extend(nodes)
        herd.sources.append(path.name)

    def index_names(node_key: str, name: str) -> None:
        for alias in alias_name_keys(name):
            herd.name_index.setdefault(alias, node_key)

    def lookup_name(name: str) -> str | None:
        for alias in alias_name_keys(name):
            hit = herd.name_index.get(alias)
            if hit and hit in herd.animals:
                return hit
        return None

    # First pass: index by AR, then by name (including "X BY Y" → X).
    for node in pending:
        if node.ar:
            existing = herd.ar_index.get(node.ar)
            if existing:
                _merge(herd.animals[existing], node)
                node.key = existing
            else:
                by_name = lookup_name(node.name)
                if by_name:
                    _merge(herd.animals[by_name], node)
                    # Promote name-only registered node to the AR key when we learn it.
                    if by_name.startswith("NM:") and node.key.startswith("AR:"):
                        herd.animals[node.key] = herd.animals.pop(by_name)
                        herd.animals[node.key].key = node.key
                        _repoint(list(herd.animals.values()) + pending, by_name, node.key)
                        if node.ar:
                            herd.ar_index[node.ar] = node.key
                        index_names(node.key, herd.animals[node.key].name)
                    else:
                        node.key = by_name
                        if node.ar:
                            herd.ar_index[node.ar] = by_name
                else:
                    herd.animals[node.key] = node
                    herd.ar_index[node.ar] = node.key
                    index_names(node.key, node.name)
        else:
            existing = lookup_name(node.name)
            if existing:
                _merge(herd.animals[existing], node)
                node.key = existing
            else:
                herd.animals[node.key] = node
                index_names(node.key, node.name)

    # Second pass: name-only nodes that later got an AR sibling, including "X BY Y".
    remap: dict[str, str] = {}
    for key, node in list(herd.animals.items()):
        if not key.startswith("NM:"):
            continue
        aliases = set(alias_name_keys(node.name))
        ar_hit = None
        for other in herd.animals.values():
            if not other.key.startswith("AR:"):
                continue
            if aliases & set(alias_name_keys(other.name)):
                ar_hit = other.key
                break
        if ar_hit:
            _merge(herd.animals[ar_hit], node)
            remap[key] = ar_hit
            del herd.animals[key]

    def fix(k: str | None) -> str | None:
        if k is None:
            return None
        return remap.get(k, k)

    sire_votes: dict[str, int] = {}
    dam_votes: dict[str, int] = {}
    for node in herd.animals.values():
        node.sire_key = fix(node.sire_key)
        node.dam_key = fix(node.dam_key)
        if node.sire_key and node.sire_key in herd.animals:
            sire_votes[node.sire_key] = sire_votes.get(node.sire_key, 0) + 1
        if node.dam_key and node.dam_key in herd.animals:
            dam_votes[node.dam_key] = dam_votes.get(node.dam_key, 0) + 1

    for key, node in herd.animals.items():
        if sire_votes.get(key) and not dam_votes.get(key):
            node.sex = "M"
        elif dam_votes.get(key) and not sire_votes.get(key):
            node.sex = "F"
        elif sire_votes.get(key) and dam_votes.get(key):
            node.sex = "M" if sire_votes[key] >= dam_votes[key] else "F"

    # Registered ids: subjects, remapped
    seen: set[str] = set()
    for sub in subjects:
        key = remap.get(sub.key, sub.key)
        # subjects without AR may have been merged into an AR node
        if key not in herd.animals:
            nk = name_key(sub.name)
            key = herd.name_index.get(nk, key)
        if key in herd.animals and key not in seen:
            herd.animals[key].registered = True
            if sub.sex and not herd.animals[key].sex:
                herd.animals[key].sex = sub.sex
            if sub.name and (
                len(sub.name) >= len(herd.animals[key].name) or not herd.animals[key].registered
            ):
                # keep the curated short name
                herd.animals[key].name = sub.name
            herd.animals[key].source = sub.source
            herd.registered_ids.append(key)
            seen.add(key)

    # Registered sex: being a parent of another *registered* animal is evidence.
    # Distant ancestor votes must not flip a leaf subject (Tayt is not a dam).
    reg_set = set(herd.registered_ids)
    sire_of_reg = {
        herd.animals[r].sire_key for r in reg_set if herd.animals[r].sire_key
    }
    dam_of_reg = {
        herd.animals[r].dam_key for r in reg_set if herd.animals[r].dam_key
    }
    for rid in herd.registered_ids:
        node = herd.animals[rid]
        looked = lookup_registered(node.source) if node.source else None
        if looked and looked[0]:
            node.name = looked[0]
        if rid in sire_of_reg and rid not in dam_of_reg:
            node.sex = "M"
        elif rid in dam_of_reg and rid not in sire_of_reg:
            node.sex = "F"
        elif looked and looked[1]:
            node.sex = looked[1]

    return herd


def _repoint(nodes: list[RawAnimal], old: str, new: str) -> None:
    if old == new:
        return
    for node in nodes:
        if node.key == old:
            node.key = new
        if node.sire_key == old:
            node.sire_key = new
        if node.dam_key == old:
            node.dam_key = new


def _merge(dst: RawAnimal, src: RawAnimal) -> None:
    if src.ar and not dst.ar:
        dst.ar = src.ar
    if src.color and not dst.color:
        dst.color = src.color
    if src.sex and not dst.sex:
        dst.sex = src.sex
    if src.registered:
        dst.registered = True
    if src.sire_key and not dst.sire_key:
        dst.sire_key = src.sire_key
    if src.dam_key and not dst.dam_key:
        dst.dam_key = src.dam_key
    if src.source and not dst.source:
        dst.source = src.source
    if src.name and (not dst.name or len(src.name) > len(dst.name)):
        # don't overwrite a curated registered name with a dirtier ancestor string
        if not dst.registered:
            dst.name = src.name
