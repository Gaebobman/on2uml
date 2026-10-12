"""Compare two versions of an ontology for change highlighting."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Association, Klass, Model


@dataclass
class Diff:
    added: set[str] = field(default_factory=set)
    changed: set[str] = field(default_factory=set)
    removed: dict[str, Klass] = field(default_factory=dict)
    assoc_added: set[tuple[str, str, str]] = field(default_factory=set)
    assoc_removed: list[Association] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"classes +{len(self.added)} ~{len(self.changed)} -{len(self.removed)}, "
            f"associations +{len(self.assoc_added)} -{len(self.assoc_removed)}"
        )


def compare(old: Model, new: Model) -> Diff:
    d = Diff()
    for iri, k in new.classes.items():
        if iri not in old.classes:
            d.added.add(iri)
        elif old.classes[iri].signature() != k.signature():
            d.changed.add(iri)
    d.removed = {iri: k for iri, k in old.classes.items() if iri not in new.classes}

    old_keys = {a.key for a in old.associations}
    new_keys = {a.key for a in new.associations}
    d.assoc_added = new_keys - old_keys
    d.assoc_removed = [a for a in old.associations if a.key not in new_keys]
    return d
