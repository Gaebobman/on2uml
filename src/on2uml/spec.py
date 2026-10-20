"""One diagram = one ViewSpec. Shared by the single-view CLI and views.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

from .diff import Diff
from .model import Model
from .overlay import load_overlay
from .puml import Options, build
from .render import render
from .view import collapse, select

CHOICES = {
    "names": ("both", "label", "name"),
    "notes": ("none", "focus", "all"),
    "color_by": ("none", "source"),
    "direction": ("tb", "lr"),
}


@dataclass
class ViewSpec:
    output: str
    focus: list[str] = field(default_factory=list)
    depth: int = 1
    subtree: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    collapse: int | None = None
    names: str = "both"
    notes: str = "focus"
    attributes: bool = True
    individuals: bool | str = False  # true | false | focus
    inherited: bool = True
    standards: bool = True
    color_by: str = "none"
    direction: str = "tb"
    title: str | None = None
    font: str | None = None
    legend: bool = True
    overlay: str | None = None
    compare: bool = True  # use the diff if one was given
    keep_puml: bool = False

    @classmethod
    def from_dict(cls, data: dict, where: str) -> "ViewSpec":
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"{where}: unknown key(s) {', '.join(unknown)}; allowed: {', '.join(sorted(known))}")
        for key in ("focus", "subtree", "exclude"):
            if isinstance(data.get(key), str):
                data[key] = [data[key]]
        spec = cls(**data)
        for key, allowed in CHOICES.items():
            if getattr(spec, key) not in allowed:
                raise ValueError(f"{where}: {key} must be one of {', '.join(allowed)}")
        if spec.individuals not in (True, False, "focus"):
            raise ValueError(f"{where}: individuals must be true, false or focus")
        return spec


@dataclass
class Result:
    path: Path
    classes: int
    warnings: list[str]


def build_source(spec: ViewSpec, model: Model, diff: Diff | None = None) -> tuple[str, int, list[str]]:
    """PlantUML source for one view, plus the number of classes drawn and warnings."""
    warnings: list[str] = []
    chosen = select(model, focus=spec.focus, depth=spec.depth, subtree=spec.subtree,
                    exclude=spec.exclude, inherited=spec.inherited)

    overlay = None
    if spec.overlay:
        overlay, ow = load_overlay(spec.overlay, model)
        warnings += ow

    focus = {model.resolve(f) for f in spec.focus}
    folded: dict[str, list[str]] = {}
    if spec.collapse is not None:
        keep = focus | (set(overlay.notes) | set(overlay.colors) if overlay else set())
        chosen, folded = collapse(model, chosen, spec.collapse, keep=keep)

    opts = Options(
        name_style=spec.names,
        notes=spec.notes,
        attributes=spec.attributes,
        individuals=spec.individuals,
        inherited=spec.inherited,
        standards=spec.standards,
        color_by=spec.color_by,
        direction=spec.direction,
        title=spec.title,
        font=spec.font,
        legend=spec.legend,
        focus=focus,
        folded=folded,
    )
    source = build(model, chosen, opts, overlay=overlay, diff=diff if spec.compare else None)
    return source, len(chosen), warnings


def output_format(path: str | Path) -> str:
    fmt = Path(path).suffix.lstrip(".").lower()
    if fmt not in ("png", "svg", "puml"):
        raise ValueError(f"unsupported output format '.{fmt}' (use .png, .svg or .puml)")
    return fmt


def generate(spec: ViewSpec, model: Model, diff: Diff | None = None, jar: str | None = None) -> Result:
    out = Path(spec.output)
    fmt = output_format(out)
    source, n_classes, warnings = build_source(spec, model, diff)

    out.parent.mkdir(parents=True, exist_ok=True)
    puml_path = out.with_suffix(".puml")
    puml_path.write_text(source, encoding="utf-8")
    if fmt == "puml":
        return Result(puml_path, n_classes, warnings)
    try:
        image = render(puml_path, fmt, jar)
    finally:
        if not spec.keep_puml:
            puml_path.unlink(missing_ok=True)
    return Result(image, n_classes, warnings)
