"""Wright path-method inbreeding and Malécot coancestry.

F of a prospective cria = coancestry of its parents.

    f_XX = (1 + F_X) / 2
    f_XY = (f_sire(X),Y + f_dam(X),Y) / 2

The recurrence is only valid when the more recent individual is expanded.
Depth is topological (0 = founder), not a parent-count heuristic: that
heuristic made parent × offspring coancestry depend on id order and
report half the true value.

Path enumeration is for barn narration. Scoring always uses the recurrence.
Incomplete pedigrees under-estimate F — missing ancestors can only add
unseen common ancestors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

DEFAULT_PEDIGREE_DEPTH = 6

BLOCK_F = 0.20
CONFIRM_F = 0.10


@dataclass(frozen=True)
class PedigreeNode:
    id: str
    sire_id: str | None = None
    dam_id: str | None = None
    name: str = ""
    known_f: float | None = None


PedigreeMap = dict[str, PedigreeNode]


@dataclass(frozen=True)
class AncestorPath:
    ancestor_id: str
    path: tuple[str, ...]
    length: int


@dataclass(frozen=True)
class CommonAncestorHit:
    ancestor_id: str
    paths_from_a: tuple[AncestorPath, ...]
    paths_from_b: tuple[AncestorPath, ...]
    contribution: float
    ancestor_f: float


@dataclass(frozen=True)
class InbreedingResult:
    animal_id: str
    F: float
    common_ancestors: tuple[CommonAncestorHit, ...]
    max_gen: int
    level: str
    percent: float
    summary: str


@dataclass
class _SideCaches:
    theta: dict[str, float] = field(default_factory=dict)
    depth: dict[str, int] = field(default_factory=dict)
    truncations: int = 0
    cycles: int = 0


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def _parents(node: PedigreeNode | None) -> tuple[str | None, str | None]:
    if node is None:
        return None, None
    sire = node.sire_id if node.sire_id else None
    dam = node.dam_id if node.dam_id else None
    return sire, dam


def _theta_key(max_gen: int, a: str, b: str) -> str:
    return f"{max_gen}|{a}|{b}" if a <= b else f"{max_gen}|{b}|{a}"


def pedigree_depth(
    animal_id: str,
    pedigree: PedigreeMap,
    side: _SideCaches,
    guard: set[str] | None = None,
) -> int:
    cached = side.depth.get(animal_id)
    if cached is not None:
        return cached
    if guard is None:
        guard = set()
    if animal_id in guard:
        side.cycles += 1
        return 0
    node = pedigree.get(animal_id)
    if node is None:
        side.depth[animal_id] = 0
        return 0
    sire, dam = _parents(node)
    if sire is None and dam is None:
        side.depth[animal_id] = 0
        return 0
    cycles_before = side.cycles
    guard.add(animal_id)
    ds = pedigree_depth(sire, pedigree, side, guard) if sire else -1
    dd = pedigree_depth(dam, pedigree, side, guard) if dam else -1
    guard.remove(animal_id)
    depth = 1 + max(ds, dd)
    if side.cycles == cycles_before:
        side.depth[animal_id] = depth
    return depth


def _expand_first(a_id: str, b_id: str, pedigree: PedigreeMap, side: _SideCaches) -> bool:
    da = pedigree_depth(a_id, pedigree, side)
    db = pedigree_depth(b_id, pedigree, side)
    if da != db:
        return da > db
    a_exp = any(_parents(pedigree.get(a_id)))
    b_exp = any(_parents(pedigree.get(b_id)))
    if a_exp != b_exp:
        return a_exp
    return a_id <= b_id


def _compute_f(
    animal_id: str,
    pedigree: PedigreeMap,
    max_gen: int,
    cache_f: dict[str, float],
    stack: set[str],
    side: _SideCaches,
) -> float:
    hit = cache_f.get(animal_id)
    if hit is not None:
        return hit
    if animal_id in stack:
        return 0.0
    node = pedigree.get(animal_id)
    if node is None:
        cache_f[animal_id] = 0.0
        return 0.0
    if node.known_f is not None:
        f = _clamp(float(node.known_f))
        cache_f[animal_id] = f
        return f
    sire, dam = _parents(node)
    if not sire or not dam:
        cache_f[animal_id] = 0.0
        return 0.0
    stack.add(animal_id)
    f = _compute_theta(sire, dam, pedigree, max_gen, cache_f, stack, side)
    stack.remove(animal_id)
    f = _clamp(f)
    cache_f[animal_id] = f
    return f


def _compute_theta(
    a_id: str,
    b_id: str,
    pedigree: PedigreeMap,
    max_gen: int,
    cache_f: dict[str, float],
    stack: set[str],
    side: _SideCaches,
    depth: int = 0,
) -> float:
    if depth > max_gen * 2 + 2:
        side.truncations += 1
        return 0.0
    key = _theta_key(max_gen, a_id, b_id)
    memo = side.theta.get(key)
    if memo is not None:
        return memo
    if a_id == b_id:
        f = _compute_f(a_id, pedigree, max_gen, cache_f, stack, side)
        self_k = (1.0 + f) / 2.0
        side.theta[key] = self_k
        return self_k
    expand_a = _expand_first(a_id, b_id, pedigree, side)
    other = b_id if expand_a else a_id
    primary = pedigree.get(a_id if expand_a else b_id)
    if primary is None:
        side.theta[key] = 0.0
        return 0.0
    sire, dam = _parents(primary)
    if sire is None and dam is None:
        side.theta[key] = 0.0
        return 0.0
    loop_key = f"theta:{key}@{depth}"
    if loop_key in stack:
        side.cycles += 1
        return 0.0
    stack.add(loop_key)
    trunc_before = side.truncations
    cycles_before = side.cycles
    total = 0.0
    parts = 0
    if sire:
        total += _compute_theta(sire, other, pedigree, max_gen, cache_f, stack, side, depth + 1)
        parts += 1
    if dam:
        total += _compute_theta(dam, other, pedigree, max_gen, cache_f, stack, side, depth + 1)
        parts += 1
    stack.remove(loop_key)
    # Missing parent is an unrelated founder (contributes 0); divisor stays 2.
    result = _clamp((total / 2.0) if parts else 0.0)
    if side.truncations == trunc_before and side.cycles == cycles_before:
        side.theta[key] = result
    return result


class WrightEngine:
    """Shared F / theta memos for one pedigree at one depth."""

    def __init__(self, pedigree: PedigreeMap, max_gen: int = DEFAULT_PEDIGREE_DEPTH) -> None:
        self.pedigree = pedigree
        self.max_gen = max_gen
        self.cache_f: dict[str, float] = {}
        self.side = _SideCaches()

    def f(self, animal_id: str) -> float:
        return _compute_f(animal_id, self.pedigree, self.max_gen, self.cache_f, set(), self.side)

    def theta(self, a_id: str, b_id: str) -> float:
        return _compute_theta(a_id, b_id, self.pedigree, self.max_gen, self.cache_f, set(), self.side)

    def offspring_f(self, dam_id: str, sire_id: str) -> float:
        return self.theta(dam_id, sire_id)

    def mean_kinship(self, animal_id: str, herd_ids: Iterable[str]) -> float:
        others = [h for h in herd_ids if h != animal_id]
        if not others:
            return 0.0
        return sum(self.theta(animal_id, other) for other in others) / len(others)

    def kinship_matrix(self, ids: list[str]) -> list[list[float]]:
        n = len(ids)
        matrix = [[0.0] * n for _ in range(n)]
        for i, a in enumerate(ids):
            for j in range(i, n):
                t = self.theta(a, ids[j])
                matrix[i][j] = t
                matrix[j][i] = t
        return matrix


def wright_f(
    animal_id: str,
    pedigree: PedigreeMap,
    max_gen: int = DEFAULT_PEDIGREE_DEPTH,
    engine: WrightEngine | None = None,
) -> float:
    eng = engine or WrightEngine(pedigree, max_gen)
    return eng.f(animal_id)


def coancestry(
    a_id: str,
    b_id: str,
    pedigree: PedigreeMap,
    max_gen: int = DEFAULT_PEDIGREE_DEPTH,
    engine: WrightEngine | None = None,
) -> float:
    eng = engine or WrightEngine(pedigree, max_gen)
    return eng.theta(a_id, b_id)


def expected_offspring_f(
    dam_id: str,
    sire_id: str,
    pedigree: PedigreeMap,
    max_gen: int = DEFAULT_PEDIGREE_DEPTH,
    engine: WrightEngine | None = None,
) -> float:
    return coancestry(dam_id, sire_id, pedigree, max_gen, engine)


def mean_kinship(
    animal_id: str,
    herd_ids: Iterable[str],
    pedigree: PedigreeMap,
    max_gen: int = DEFAULT_PEDIGREE_DEPTH,
    engine: WrightEngine | None = None,
) -> float:
    eng = engine or WrightEngine(pedigree, max_gen)
    return eng.mean_kinship(animal_id, herd_ids)


def interpret_f(f: float) -> tuple[str, float, str]:
    f = _clamp(f)
    pct = round(f * 100.0, 2)
    if f < 0.03125:
        return (
            "negligible",
            pct,
            f"F={pct:.2f}% is negligible for most breeding programs.",
        )
    if f < 0.0625:
        return (
            "low",
            pct,
            f"F={pct:.2f}% is low (below first-cousin equivalent ~6.25%).",
        )
    if f < 0.125:
        return (
            "moderate",
            pct,
            f"F={pct:.2f}% is moderate (half-sib / first-cousin range).",
        )
    if f < 0.25:
        return (
            "high",
            pct,
            f"F={pct:.2f}% is high (full-sib / parent-offspring territory).",
        )
    return (
        "severe",
        pct,
        f"F={pct:.2f}% is severe; expect elevated inbreeding-depression risk.",
    )


def verdict_for(f: float, structural: str | None = None) -> str:
    """Barn verdict. Structural parent-offspring / full-sib always BLOCK."""
    if structural in {"parent_offspring", "full_sib"}:
        return "BLOCK"
    if f >= BLOCK_F:
        return "BLOCK"
    if f >= CONFIRM_F:
        return "CONFIRM"
    return "PROCEED"


def build_ancestor_paths(
    animal_id: str,
    pedigree: PedigreeMap,
    max_gen: int = DEFAULT_PEDIGREE_DEPTH,
) -> list[AncestorPath]:
    results: list[AncestorPath] = []

    def dfs(current: str, path: list[str], depth: int) -> None:
        if depth > max_gen:
            return
        if depth > 0:
            results.append(AncestorPath(current, tuple(path), depth))
        if depth == max_gen:
            return
        node = pedigree.get(current)
        if node is None:
            return
        sire, dam = _parents(node)
        if sire and sire not in path:
            dfs(sire, path + [sire], depth + 1)
        if dam and dam not in path:
            dfs(dam, path + [dam], depth + 1)

    dfs(animal_id, [animal_id], 0)
    return results


def _paths_independent(path_a: tuple[str, ...], path_b: tuple[str, ...]) -> bool:
    set_a = set(path_a[:-1])
    return all(node not in set_a for node in path_b[:-1])


def _group_paths(paths: Iterable[AncestorPath]) -> dict[str, list[AncestorPath]]:
    grouped: dict[str, list[AncestorPath]] = {}
    for path in paths:
        grouped.setdefault(path.ancestor_id, []).append(path)
    return grouped


def wright_paths(
    dam_id: str,
    sire_id: str,
    pedigree: PedigreeMap,
    max_gen: int = DEFAULT_PEDIGREE_DEPTH,
    engine: WrightEngine | None = None,
) -> tuple[float, list[CommonAncestorHit]]:
    """Path contributions to F of dam × sire. Scoring number is still coancestry."""
    eng = engine or WrightEngine(pedigree, max_gen)
    scored = eng.theta(dam_id, sire_id)
    dam_paths = [AncestorPath(dam_id, (dam_id,), 0), *build_ancestor_paths(dam_id, pedigree, max_gen)]
    sire_paths = [AncestorPath(sire_id, (sire_id,), 0), *build_ancestor_paths(sire_id, pedigree, max_gen)]
    by_dam = _group_paths(dam_paths)
    by_sire = _group_paths(sire_paths)
    hits: list[CommonAncestorHit] = []
    for ancestor_id, paths_a in by_dam.items():
        paths_b = by_sire.get(ancestor_id)
        if not paths_b:
            continue
        ancestor_f = eng.f(ancestor_id)
        contribution = 0.0
        kept_a: list[AncestorPath] = []
        kept_b: list[AncestorPath] = []
        for p_a in paths_a:
            for p_b in paths_b:
                if dam_id != sire_id and not _paths_independent(p_a.path, p_b.path):
                    continue
                n1, n2 = p_a.length, p_b.length
                # Contribution to F = (1/2)^(n1+n2+1) * (1+F_A)
                contribution += (2 ** -(n1 + n2 + 1)) * (1.0 + ancestor_f)
                kept_a.append(p_a)
                kept_b.append(p_b)
        if contribution > 1e-12:
            hits.append(
                CommonAncestorHit(
                    ancestor_id=ancestor_id,
                    paths_from_a=tuple(paths_a),
                    paths_from_b=tuple(paths_b),
                    contribution=contribution,
                    ancestor_f=ancestor_f,
                )
            )
    hits.sort(key=lambda h: h.contribution, reverse=True)
    return scored, hits


def analyze_inbreeding(
    animal_id: str,
    pedigree: PedigreeMap,
    max_gen: int = DEFAULT_PEDIGREE_DEPTH,
    engine: WrightEngine | None = None,
) -> InbreedingResult:
    eng = engine or WrightEngine(pedigree, max_gen)
    node = pedigree.get(animal_id)
    if node is None:
        level, pct, summary = interpret_f(0.0)
        return InbreedingResult(animal_id, 0.0, (), max_gen, level, pct, summary)
    sire, dam = _parents(node)
    if not sire or not dam:
        f = eng.f(animal_id)
        level, pct, summary = interpret_f(f)
        return InbreedingResult(animal_id, f, (), max_gen, level, pct, summary)
    f, hits = wright_paths(dam, sire, pedigree, max_gen, eng)
    # Prefer recurrence F (paths can truncate).
    f = eng.f(animal_id)
    level, pct, summary = interpret_f(f)
    return InbreedingResult(animal_id, f, tuple(hits), max_gen, level, pct, summary)


def structural_relationship(
    a_id: str,
    b_id: str,
    pedigree: PedigreeMap,
) -> str | None:
    """Cheap structural tag used to force BLOCK on close kin even if F is truncated."""
    if a_id == b_id:
        return "self"
    a = pedigree.get(a_id)
    b = pedigree.get(b_id)
    a_sire, a_dam = _parents(a)
    b_sire, b_dam = _parents(b)
    if a_id in {b_sire, b_dam} or b_id in {a_sire, a_dam}:
        return "parent_offspring"
    if a_sire and a_dam and a_sire == b_sire and a_dam == b_dam:
        return "full_sib"
    if a_sire and a_sire == b_sire:
        return "paternal_half_sib"
    if a_dam and a_dam == b_dam:
        return "maternal_half_sib"
    a_gps = {p for p in (a_sire, a_dam) if p}
    if a and b:
        if b_id in a_gps or a_id in {p for p in (b_sire, b_dam) if p}:
            return "grandparent"
        # niece/nephew via parent being full/half sib — leave to F
    return None


def completeness(
    subject_id: str,
    sire_id: str | None,
    dam_id: str | None,
    pedigree: PedigreeMap,
    max_gen: int = DEFAULT_PEDIGREE_DEPTH,
) -> dict:
    """MacCluer completeness + equivalent complete generations.

    Positions, not distinct ancestors: an animal on both sides fills two slots,
    which is exactly what creates F.
    """
    max_gen = max(0, min(int(max_gen), 16))
    by_gen = []
    frontier: list[str | None] = [sire_id or None, dam_id or None]
    ecg = 0.0
    named_absent = 0
    deepest = 0
    for g in range(1, max_gen + 1):
        expected = 2**g
        nxt: list[str | None] = []
        known = 0
        for ident in frontier:
            if ident is None:
                nxt.extend([None, None])
                continue
            known += 1
            ecg += 2.0 ** -g
            node = pedigree.get(ident)
            if node is None:
                named_absent += 1
                nxt.extend([None, None])
                continue
            sire, dam = _parents(node)
            nxt.extend([sire, dam])
        if known:
            deepest = g
        by_gen.append(
            {
                "generation": g,
                "known": known,
                "expected": expected,
                "proportion": round(known / expected, 6),
            }
        )
        frontier = nxt
    index = sum(g["proportion"] for g in by_gen) / len(by_gen) if by_gen else 0.0
    both = bool(sire_id and dam_id)
    if not both and index == 0:
        level = "none"
    elif index >= 0.95:
        level = "complete"
    elif index >= 0.75:
        level = "good"
    elif index >= 0.4:
        level = "partial"
    elif index > 0:
        level = "shallow"
    else:
        level = "none"
    may_under = (not both) or index < 0.5
    return {
        "subject_id": subject_id,
        "max_gen": max_gen,
        "by_generation": by_gen,
        "index": round(index, 4),
        "equivalent_complete_generations": round(ecg, 4),
        "deepest_known_generation": deepest,
        "both_parents_known": both,
        "named_but_absent": named_absent,
        "level": level,
        "may_underestimate_f": may_under,
    }


def iter_ancestors(animal_id: str, pedigree: PedigreeMap) -> Iterator[str]:
    seen: set[str] = set()
    stack = [animal_id]
    while stack:
        current = stack.pop()
        node = pedigree.get(current)
        if node is None:
            continue
        for parent in _parents(node):
            if parent and parent not in seen:
                seen.add(parent)
                yield parent
                stack.append(parent)


def founder_ids(animal_id: str, pedigree: PedigreeMap) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def walk(ident: str) -> None:
        if ident in seen:
            return
        seen.add(ident)
        node = pedigree.get(ident)
        sire, dam = _parents(node)
        if sire is None and dam is None:
            found.append(ident)
            return
        if sire:
            walk(sire)
        if dam:
            walk(dam)
        if node is None:
            found.append(ident)

    walk(animal_id)
    return found
