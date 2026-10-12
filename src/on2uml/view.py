"""Pick which classes go into one diagram (a 'view')."""

from __future__ import annotations

from collections import defaultdict

from .model import Association, Model


def inherited_associations(model: Model, iri: str) -> list[tuple[Association, str, str]]:
    """Associations a class gets from its ancestors.

    Returns (association, ancestor, end) where end is "domain" when the ancestor is
    the association's source and "range" when it is the target.
    """
    out = []
    for anc in model.ancestors(iri):
        for a in model.associations:
            if a.domain == anc:
                out.append((a, anc, "domain"))
            if a.range == anc:
                out.append((a, anc, "range"))
    return out


def _neighbors(model: Model, inherit_for: set[str] = frozenset()) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for k in model.classes.values():
        for p in k.parents + k.equivalents:
            adj[k.iri].add(p)
            adj[p].add(k.iri)
    for a in model.associations:
        adj[a.domain].add(a.range)
        adj[a.range].add(a.domain)
    for iri in inherit_for:
        for a, _, end in inherited_associations(model, iri):
            other = a.range if end == "domain" else a.domain
            adj[iri].add(other)
            adj[other].add(iri)
    return adj


def _descendants(model: Model, root: str) -> set[str]:
    children: dict[str, set[str]] = defaultdict(set)
    for k in model.classes.values():
        for p in k.parents:
            children[p].add(k.iri)
    seen, stack = {root}, [root]
    while stack:
        for c in children[stack.pop()]:
            if c not in seen:
                seen.add(c)
                stack.append(c)
    return seen


def _matches(model: Model, iri: str, pattern: str) -> bool:
    k = model.classes[iri]
    return pattern in iri or pattern in (k.name, k.label)


def select(
    model: Model,
    focus: list[str] = (),
    depth: int = 1,
    subtree: list[str] = (),
    exclude: list[str] = (),
    inherited: bool = True,
) -> set[str]:
    """Return the class IRIs to draw.

    focus   -- classes to centre on; keeps everything within `depth` hops
               (inheritance + associations, both directions)
    subtree -- classes whose whole descendant tree is kept
    exclude -- IRI substrings, local names or labels to drop (e.g. an upper ontology namespace)
    inherited -- focus classes also reach the far ends of associations defined on their ancestors
    With neither focus nor subtree, every class is kept.
    """
    unknown = [r for r in [*focus, *subtree] if model.resolve(r) not in model.classes]
    if unknown:
        raise ValueError(f"unknown class: {', '.join(unknown)}")

    if not focus and not subtree:
        chosen = set(model.classes)
    else:
        chosen = set()
        for ref in subtree:
            chosen |= _descendants(model, model.resolve(ref))
        adj = _neighbors(model, {model.resolve(f) for f in focus} if inherited else set())
        for ref in focus:
            frontier = {model.resolve(ref)}
            chosen |= frontier
            for _ in range(depth):
                frontier = {n for f in frontier for n in adj[f]} - chosen
                chosen |= frontier

    chosen &= set(model.classes)
    focus_iris = {model.resolve(f) for f in focus}
    # Focus classes are never excluded: a shared `exclude` default must not empty a class's own diagram.
    return {c for c in chosen if c in focus_iris or not any(_matches(model, c, pat) for pat in exclude)}


def collapse(model: Model, chosen: set[str], threshold: int, keep: set[str] = frozenset()) -> tuple[set[str], dict[str, list[str]]]:
    """Fold plain leaf subclasses into their parent when a parent has more than `threshold`.

    A leaf is 'plain' when it has no subclasses, no attributes, takes part in no
    association and is not in `keep`. Returns the reduced class set and, per parent,
    the labels of the classes folded into it.
    """
    has_children = {p for k in model.classes.values() for p in k.parents}
    in_assoc = {e for a in model.associations for e in (a.domain, a.range)}

    by_parent: dict[str, list[str]] = defaultdict(list)
    for iri in chosen:
        k = model.classes[iri]
        if iri in has_children or iri in in_assoc or iri in keep or k.attributes or len(k.parents) != 1:
            continue
        if k.parents[0] in chosen:
            by_parent[k.parents[0]].append(iri)

    folded: dict[str, list[str]] = {}
    reduced = set(chosen)
    for parent, leaves in by_parent.items():
        if len(leaves) > threshold:
            reduced -= set(leaves)
            folded[parent] = sorted(model.classes[c].label or model.classes[c].name for c in leaves)
    return reduced, folded
