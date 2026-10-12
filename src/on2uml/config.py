"""views.yaml: render several diagrams of one ontology in one go.

    ontology: ../ontology.ttl        # paths are relative to this file
    compare: ../ontology_v1.2.ttl    # optional; views opt out with `compare: false`
    lang: ko
    namespaces:                      # optional: extra standard ontologies -> «NAME»
      "https://std.example.com/core#": CORP
    output_dir: out
    format: png                      # png | svg | puml
    defaults:                        # applied to every view, overridable per view
      exclude: [obolibrary]
      collapse: 3
    views:
      - name: overview               # -> out/overview.png
        title: 도메인 개요
        names: label
        notes: none
        attributes: false
        color_by: source
        direction: lr
      - name: truck
        focus: Truck
        overlay: report-notes.yaml
    per_class:                       # optional: one detail diagram per class (see perclass.py)
      classes: all
      output_dir: out/classes

View keys are the same as the CLI options (dashes become underscores).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .perclass import PerClass
from .perclass import parse as parse_per_class
from .spec import ViewSpec

TOP_KEYS = {"ontology", "compare", "lang", "namespaces", "output_dir", "format", "defaults", "views", "per_class"}


@dataclass
class Config:
    ontology: Path
    compare: Path | None
    lang: str | None
    namespaces: dict[str, str]
    views: dict[str, ViewSpec]
    per_class: PerClass | None = None


def load_config(path: str | Path) -> Config:
    path = Path(path)
    base = path.parent
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    unknown = sorted(set(raw) - TOP_KEYS)
    if unknown:
        raise ValueError(f"{path}: unknown top-level key(s) {', '.join(unknown)}")
    if "ontology" not in raw:
        raise ValueError(f"{path}: 'ontology' is required")
    if not raw.get("views") and not raw.get("per_class"):
        raise ValueError(f"{path}: give at least one entry under 'views' or a 'per_class' block")

    fmt = raw.get("format", "png")
    out_dir = base / raw.get("output_dir", "out")
    defaults = raw.get("defaults") or {}

    views: dict[str, ViewSpec] = {}
    for i, v in enumerate(raw.get("views") or []):
        v = dict(v)
        name = v.pop("name", None)
        if not name:
            raise ValueError(f"{path}: view #{i + 1} needs a 'name'")
        if name in views or name == "per_class":
            raise ValueError(f"{path}: duplicate view name '{name}'")
        data = {**defaults, **v}
        data.setdefault("output", str(out_dir / f"{name}.{fmt}"))
        if data.get("overlay"):
            data["overlay"] = str(base / data["overlay"])
        views[name] = ViewSpec.from_dict(data, where=f"{path.name} view '{name}'")

    return Config(
        ontology=base / raw["ontology"],
        compare=base / raw["compare"] if raw.get("compare") else None,
        lang=raw.get("lang", "ko"),
        namespaces={str(k): str(v) for k, v in (raw.get("namespaces") or {}).items()},
        views=views,
        per_class=parse_per_class(raw["per_class"] or {}, defaults, base, fmt, f"{path.name} per_class")
        if "per_class" in raw else None,
    )
