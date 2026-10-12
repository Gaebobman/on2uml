"""Report-only annotations kept outside the ontology.

Example overlay.yaml:

    title: 차량 중심 뷰 (v1.3)
    notes:
      Truck: 이번 분기 속성 3개 추가
      제조사: 제조사 클래스는 registry 출처      # label works too
    hide: [Thing]
    colors:
      Truck: "#ffd6d6"

Keys may be a full IRI, a local name, or an rdfs:label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .model import Model


@dataclass
class Overlay:
    title: str | None = None
    notes: dict[str, str] = field(default_factory=dict)
    hide: set[str] = field(default_factory=set)
    colors: dict[str, str] = field(default_factory=dict)


def load_overlay(path: str | Path, model: Model) -> tuple[Overlay, list[str]]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    warnings: list[str] = []

    def resolve(ref: str) -> str | None:
        iri = model.resolve(str(ref))
        if iri is None:
            warnings.append(f"overlay: '{ref}' not found in ontology")
        return iri

    ov = Overlay(title=raw.get("title"))
    for ref, text in (raw.get("notes") or {}).items():
        if iri := resolve(ref):
            ov.notes[iri] = str(text)
    for ref in raw.get("hide") or []:
        if iri := resolve(ref):
            ov.hide.add(iri)
    for ref, color in (raw.get("colors") or {}).items():
        if iri := resolve(ref):
            ov.colors[iri] = str(color)
    return ov, warnings
