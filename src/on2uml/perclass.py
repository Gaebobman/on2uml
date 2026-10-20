"""One detail diagram per class, with change tracking between runs.

views.yaml:

    per_class:
      classes: all            # all | domain (skip standard-ontology classes) | [Class, ...]
      output_dir: out/classes
      format: png             # defaults to the top-level format
      depth: 1                # any view key; merged over `defaults`
      individuals: true       # or focus: only the individuals of the class itself
      individuals_hide: [Concept]  # but never those of these classes (wins over focus)

Each run writes, per class, <Name>.puml and <Name>.<format>, plus:
  manifest.json  class -> sha256 of its .puml (no timestamps, so it diffs cleanly in git)
  index.md       table of every class image + what changed since the previous run

Only diagrams whose .puml changed are re-rendered. Images of classes that disappeared
from the ontology are deleted (only files listed in the previous manifest are touched).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, fields
from pathlib import Path

from .diff import Diff
from .model import Model
from .render import render_many
from .spec import ViewSpec, build_source

MANIFEST = "manifest.json"
INDEX = "index.md"
OWN_KEYS = {"classes", "output_dir", "format"}
EXCLUDED_VIEW_KEYS = {"output", "focus", "subtree", "title"}  # set per class


@dataclass
class PerClass:
    classes: str | list[str]
    output_dir: Path
    fmt: str
    template: dict  # ViewSpec keys shared by every class diagram


@dataclass
class Report:
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"added {len(self.added)}, changed {len(self.changed)}, "
                f"removed {len(self.removed)}, unchanged {self.unchanged}")


def parse(raw: dict, defaults: dict, base: Path, fmt: str, where: str) -> PerClass:
    view_keys = {f.name for f in fields(ViewSpec)} - EXCLUDED_VIEW_KEYS
    unknown = sorted(set(raw) - OWN_KEYS - view_keys)
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {', '.join(unknown)}; "
                         f"allowed: {', '.join(sorted(OWN_KEYS | view_keys))}")
    template = {k: v for k, v in {**defaults, **raw}.items() if k in view_keys}
    if template.get("overlay"):
        template["overlay"] = str(base / template["overlay"])
    # Validate the template once, up front.
    ViewSpec.from_dict({**template, "output": "x.png"}, where=where)
    classes = raw.get("classes", "all")
    if isinstance(classes, str) and classes not in ("all", "domain"):
        classes = [classes]
    pc_fmt = raw.get("format", fmt)
    if pc_fmt not in ("png", "svg"):
        raise ValueError(f"{where}: format must be png or svg")
    return PerClass(classes=classes, output_dir=base / raw.get("output_dir", "out/classes"),
                    fmt=pc_fmt, template=template)


def _targets(pc: PerClass, model: Model) -> list[str]:
    if pc.classes == "all":
        return sorted(model.classes)
    if pc.classes == "domain":
        return sorted(i for i, k in model.classes.items() if not k.standard)
    out = []
    for ref in pc.classes:
        iri = model.resolve(str(ref))
        if iri not in model.classes:
            raise ValueError(f"per_class: unknown class '{ref}'")
        out.append(iri)
    return out


def _stems(model: Model, iris: list[str]) -> dict[str, str]:
    """File name per class: the local name, made unique and filesystem-safe."""
    stems: dict[str, str] = {}
    used: set[str] = set()
    for iri in iris:
        base = re.sub(r"[^0-9A-Za-z_.-]", "_", model.classes[iri].name) or "class"
        stem, n = base, 2
        while stem.lower() in used:  # case-insensitive filesystems
            stem, n = f"{base}_{n}", n + 1
        used.add(stem.lower())
        stems[iri] = stem
    return stems


def _title(model: Model, iri: str) -> str:
    k = model.classes[iri]
    name = k.label or k.name
    if k.label and k.label != k.name:
        name = f"{k.label} ({k.name})"
    return f"«{k.standard}» {name}" if k.standard else name


def run(pc: PerClass, model: Model, diff: Diff | None = None, jar: str | None = None,
        ontology_name: str = "") -> Report:
    out = pc.output_dir
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / MANIFEST
    previous = {}
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8")).get("classes", {})

    report = Report()
    targets = _targets(pc, model)
    stems = _stems(model, targets)
    current: dict[str, dict] = {}
    to_render: list[Path] = []

    for iri in targets:
        stem = stems[iri]
        spec = ViewSpec.from_dict(
            {**pc.template, "output": str(out / f"{stem}.{pc.fmt}"), "focus": [iri], "title": _title(model, iri)},
            where=f"per_class {stem}",
        )
        source, _, warnings = build_source(spec, model, diff)
        report.warnings += warnings
        digest = hashlib.sha256(f"{pc.fmt}\n{source}".encode()).hexdigest()
        k = model.classes[iri]
        current[stem] = {"iri": iri, "label": k.label, "standard": k.standard, "sha256": digest}

        puml = out / f"{stem}.puml"
        image = out / f"{stem}.{pc.fmt}"
        old = previous.get(stem)
        if old and old.get("sha256") == digest and image.exists() and puml.exists():
            report.unchanged += 1
            continue
        (report.changed if old else report.added).append(stem)
        puml.write_text(source, encoding="utf-8")
        to_render.append(puml)

    render_many(to_render, pc.fmt, jar)

    for stem in sorted(set(previous) - set(current)):
        report.removed.append(stem)
        for ext in ("puml", "png", "svg"):
            (out / f"{stem}.{ext}").unlink(missing_ok=True)

    manifest = {"ontology": ontology_name, "format": pc.fmt, "classes": dict(sorted(current.items()))}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / INDEX).write_text(_index(current, report, pc.fmt, ontology_name), encoding="utf-8")
    report.warnings = sorted(set(report.warnings))
    return report


def _index(current: dict[str, dict], report: Report, fmt: str, ontology_name: str) -> str:
    def link(stem: str) -> str:
        return f"[{stem}]({stem}.{fmt})"

    lines = [f"# 클래스별 다이어그램{f' — {ontology_name}' if ontology_name else ''}", ""]
    lines += ["## 마지막 생성에서 바뀐 그림", ""]
    if not (report.added or report.changed or report.removed):
        lines += ["변경 없음.", ""]
    else:
        lines += [
            "그림 단위 변경이다. 상위 클래스의 관계·속성이 바뀌면 그걸 상속해 보여 주는 하위 클래스 그림도 함께 바뀐다.",
            "",
        ]
        for title, items, linked in (("추가", report.added, True), ("변경", report.changed, True),
                                     ("삭제", report.removed, False)):
            if items:
                shown = ", ".join(link(s) if linked else s for s in items)
                lines += [f"- **{title} {len(items)}**: {shown}", ""]

    lines += ["## 전체 목록", "", "| 클래스 | 이름 | 표준 | 그림 |", "|---|---|---|---|"]
    order = sorted(current.items(), key=lambda kv: (kv[1]["standard"] or "", kv[1]["label"] or kv[0]))
    for stem, meta in order:
        label = (meta["label"] or "").replace("|", "\\|")
        lines.append(f"| {label} | {stem} | {meta['standard'] or ''} | {link(stem)} |")
    return "\n".join(lines) + "\n"
