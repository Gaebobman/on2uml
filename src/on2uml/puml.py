"""Build PlantUML class-diagram source from a Model."""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field

from .diff import Diff
from .model import Klass, Model
from .overlay import Overlay
from .view import inherited_associations

ADDED, CHANGED, REMOVED = "#d4f4dd", "#ffe7b3", "#eeeeee"
STANDARD_BG = "#f1f3f5"
ADDED_EDGE, REMOVED_EDGE, INHERITED_EDGE = "#2e9e5b", "#999999", "#8a8fb5"
SOURCE_PALETTE = ["#dbeafe", "#fce7f3", "#e0f2e9", "#fef3c7", "#ede9fe", "#ffedd5"]


@dataclass
class Options:
    name_style: str = "both"  # label | name | both
    notes: str = "focus"  # none | focus | all
    attributes: bool = True
    individuals: bool | str = False  # False | True (every drawn class) | "focus" (focus classes only)
    inherited: bool = True  # replay ancestors' attributes/associations on focus classes
    standards: bool = True  # «BFO»/«IOF» stereotypes on classes from standard ontologies
    color_by: str = "none"  # none | source
    direction: str = "tb"  # tb | lr
    title: str | None = None
    font: str | None = None
    legend: bool = True  # explain the notation used in this diagram
    note_width: int = 28
    focus: set[str] = field(default_factory=set)
    folded: dict[str, list[str]] = field(default_factory=dict)  # parent IRI -> folded leaf labels


class _Aliases:
    def __init__(self):
        self._by_iri: dict[str, str] = {}
        self._used: set[str] = set()

    def __call__(self, iri: str, name: str, prefix: str = "C") -> str:
        if iri not in self._by_iri:
            base = f"{prefix}_{re.sub(r'[^0-9A-Za-z_]', '_', name)}"
            alias, n = base, 2
            while alias in self._used:
                alias, n = f"{base}_{n}", n + 1
            self._used.add(alias)
            self._by_iri[iri] = alias
        return self._by_iri[iri]


def _q(text: str) -> str:
    return text.replace('"', "''")


def _display(label: str | None, name: str, style: str) -> str:
    if style == "name" or not label:
        return name
    if style == "label" or label == name:
        return label
    return f"{label}\\n<size:10><color:#666666>{name}</color></size>"


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for para in text.splitlines() or [""]:
        lines.extend(textwrap.wrap(para, width=width) or [""])
    return lines


# Notation legend rows, in display order. Only the rows whose key was drawn are shown.
NOTATION = [
    ("inherit", "자식 ──▷ 부모", "상속: 자식은 부모의 한 종류 (subClassOf)"),
    ("assoc", "A ──> B : 이름", "관계: A가 B를 '이름'으로 가리킴 (ObjectProperty)"),
    ("mult", "──> 1..*", "끝의 숫자: B 쪽 개수 (1..* 1개 이상, 0..1 최대 1개)"),
    ("only", "«only»", "B 종류만 올 수 있음 (allValuesFrom)"),
    ("inherited_edge", f"<color:{INHERITED_EDGE}>A - - > B</color>",
     "그림 밖 상위 클래스에서 물려받은 관계"),
    ("equiv", "A ┈┈ B : ≡", "같은 클래스 (equivalentClass)"),
    ("instance", "개체 ┈┈> 클래스", "개체가 속한 클래스 (instanceOf)"),
    ("attr", "이름 : 타입", "박스 안 줄: 값 속성 (DatatypeProperty)"),
    ("attr_extra", "[1..*]  = 값", "속성 개수 제약 / 고정값 (Restriction)"),
    ("inherited_attrs", "<color:#777777>.. X에서 상속 ..</color>", "X에서 물려받은 속성"),
    ("folded", ".. 하위 클래스 N개 ..", "그림을 줄이려 접어 둔 하위 클래스"),
    ("note", "<back:#fffbe6> 노란 메모 </back>", "클래스 설명 (rdfs:comment)"),
]


def build(model: Model, chosen: set[str], opts: Options, overlay: Overlay | None = None, diff: Diff | None = None) -> str:
    overlay = overlay or Overlay()
    used: set[str] = set()  # NOTATION keys drawn in this diagram
    alias = _Aliases()
    visible = chosen - overlay.hide
    ghosts: dict[str, Klass] = {}
    if diff:
        # Removed classes are drawn as dashed ghosts: all of them in a full view,
        # otherwise only those whose parent is still on the diagram.
        full_view = chosen >= set(model.classes)
        ghosts = {
            iri: k for iri, k in diff.removed.items()
            if full_view or any(p in visible for p in k.parents)
        }

    source_colors: dict[str, str] = {}
    if opts.color_by == "source":
        sources = sorted({model.classes[c].source for c in visible if model.classes[c].source})
        source_colors = {s: SOURCE_PALETTE[i % len(SOURCE_PALETTE)] for i, s in enumerate(sources)}

    out = ["@startuml"]
    if opts.direction == "lr":
        out.append("left to right direction")
    out += [
        "hide circle",
        "hide empty members",
        "skinparam shadowing false",
        "skinparam classAttributeIconSize 0",
        "skinparam class {",
        "  BackgroundColor #ffffff",
        "  BorderColor #555555",
        "  ArrowColor #555555",
        "}",
        "skinparam legend {",
        "  BackgroundColor #fafafa",
        "  BorderColor #bbbbbb",
        "  FontSize 12",
        "}",
        "skinparam note {",
        "  BackgroundColor #fffbe6",
        "  BorderColor #c9b458",
        "}",
    ]
    if opts.font:
        out.append(f'skinparam defaultFontName "{opts.font}"')
    title = overlay.title or opts.title
    if title:
        out.append(f"title {_q(title)}")
    out.append("")

    def class_color(iri: str) -> str:
        if iri in overlay.colors:
            return overlay.colors[iri]
        if diff and iri in diff.added:
            return ADDED
        if diff and iri in diff.changed:
            return CHANGED
        k = model.classes[iri]
        if k.source in source_colors:
            return source_colors[k.source]
        return STANDARD_BG if opts.standards and k.standard else ""

    def attr_line(at, muted: bool = False) -> str:
        # PlantUML can't nest <color> tags, so each part gets its own.
        main, sub = ("#777777", "#999999") if muted else (None, "#666666")

        def paint(text: str, color: str | None) -> str:
            return f"<color:{color}>{text}</color>" if color else text

        name = paint(_display(at.label, at.name, "label" if opts.name_style == "label" else "name"), main)
        if opts.name_style == "both" and at.label and at.label != at.name:
            name = f"{paint(at.label, main)} {paint(at.name, sub)}"
        tail = f" = {at.value}" if at.value else (f" : {at.range}" if at.range else "")
        if at.mult:
            tail += f" [{at.mult}]"
        used.add("attr_extra" if at.mult or at.value else "attr")
        line = name + paint(tail, main)
        return f"  {{field}} {_q(line)}"

    # Ancestors that are off the diagram still matter for focus classes: their
    # attributes are listed in the focus box, their associations drawn as dashed edges.
    replay_from: dict[str, list[str]] = {}
    if opts.inherited:
        for f in sorted(opts.focus & visible):
            replay_from[f] = [a for a in model.ancestors(f) if a in model.classes and a not in visible]

    def emit_class(k: Klass, style: str = "") -> None:
        a = alias(k.iri, k.name)
        head = f'class "{_q(_display(k.label, k.name, opts.name_style))}" as {a}'
        if opts.standards and k.standard:
            head += f" <<{k.standard}>>"
        if style:
            head += f" {style}"
        attrs = k.attributes if opts.attributes else []
        inherited = [
            (anc, model.classes[anc].attributes)
            for anc in replay_from.get(k.iri, [])
            if opts.attributes and model.classes[anc].attributes
        ]
        folded = opts.folded.get(k.iri, [])
        if not attrs and not folded and not inherited:
            out.append(head)
            return
        out.append(head + " {")
        out.extend(attr_line(at) for at in attrs)
        for anc, anc_attrs in inherited:
            used.add("inherited_attrs")
            anc_k = model.classes[anc]
            out.append(f"  .. {_q(anc_k.label or anc_k.name)}에서 상속 ..")
            out.extend(attr_line(at, muted=True) for at in anc_attrs)
        if folded:
            used.add("folded")
            out.append(f"  .. 하위 클래스 {len(folded)}개 ..")
            for line in textwrap.wrap(", ".join(folded), width=40):
                out.append(f"  {{field}} <size:10><color:#666666>{_q(line)}</color></size>")
        out.append("}")

    for iri in sorted(visible, key=lambda i: model.classes[i].name):
        emit_class(model.classes[iri], class_color(iri))
    for k in sorted(ghosts.values(), key=lambda k: k.name):
        emit_class(k, f"{REMOVED};line.dashed;text:888888")
    out.append("")

    drawn = visible | set(ghosts)
    for iri in sorted(drawn):
        k = model.classes.get(iri) or ghosts[iri]
        for p in k.parents:
            if p in drawn:
                edge = "<|-[#999999,dashed]-" if iri in ghosts else "<|--"
                used.add("inherit")
                out.append(f"{alias(p, (model.classes.get(p) or ghosts[p]).name)} {edge} {alias(iri, k.name)}")
    seen_equiv: set[frozenset] = set()
    for iri in sorted(visible):
        for e in model.classes[iri].equivalents:
            pair = frozenset((iri, e))
            if e in visible and pair not in seen_equiv:
                seen_equiv.add(pair)
                used.add("equiv")
                out.append(f"{alias(iri, model.classes[iri].name)} .. {alias(e, model.classes[e].name)} : ≡")

    def assoc_label(label: str | None, name: str) -> str:
        if opts.name_style == "name" or not label:
            return name
        if opts.name_style == "label":
            return label
        return f"{label}\\n<size:9><color:#666666>{name}</color></size>"

    def edge(a, src: str, dst: str, arrow: str, suffix: str = "") -> str:
        lbl = assoc_label(a.label, a.name)
        used.add("assoc")
        if a.qualifier:
            lbl += f" «{a.qualifier}»"
            used.add(a.qualifier if a.qualifier == "only" else "assoc")
        if a.mult:
            used.add("mult")
        mult = f' "{a.mult}"' if a.mult else ""
        return f"{src} {arrow}{mult} {dst} : {_q(lbl + suffix)}"

    def name_of(iri: str) -> str:
        return (model.classes.get(iri) or ghosts[iri]).name

    # A property declared with rdfs:domain/range and also restricted on the same
    # class pair is one edge; the restriction contributes the multiplicity.
    merged: dict[tuple[str, str, str], tuple] = {}
    for a in model.associations:
        k = (a.iri, a.domain, a.range)
        prev = merged.get(k)
        keys = (prev[1] if prev else set()) | {a.key}
        merged[k] = (a if a.kind == "restriction" or not prev else prev[0], keys)
    for a, keys in merged.values():
        if a.domain in visible and a.range in visible:
            arrow = "-->"
            if diff and keys & diff.assoc_added:
                arrow = f"-[{ADDED_EDGE},bold]->"
            out.append(edge(a, alias(a.domain, name_of(a.domain)), alias(a.range, name_of(a.range)), arrow))
    if diff:
        for a in diff.assoc_removed:
            if a.domain in drawn and a.range in drawn and (a.iri, a.domain, a.range) not in merged:
                out.append(edge(a, alias(a.domain, name_of(a.domain)), alias(a.range, name_of(a.range)),
                                f"-[{REMOVED_EDGE},dashed]->"))

    seen_inh: set[tuple] = set()
    for f, ancestors in replay_from.items():
        hidden = set(ancestors)
        for a, anc, end in inherited_associations(model, f):
            other = a.range if end == "domain" else a.domain
            key = (a.iri, f, other, end)
            if anc not in hidden or other not in visible or key in seen_inh:
                continue
            seen_inh.add(key)
            used.add("inherited_edge")
            anc_k = model.classes[anc]
            suffix = f"\\n<size:9>({anc_k.label or anc_k.name}에서 상속)</size>"
            src, dst = (f, other) if end == "domain" else (other, f)
            out.append(edge(a, alias(src, name_of(src)), alias(dst, name_of(dst)),
                            f"-[{INHERITED_EDGE},dashed]->", suffix))

    if opts.individuals:
        out.append("")
        for ind in sorted(model.individuals.values(), key=lambda i: i.name):
            types = [t for t in ind.types if t in (opts.focus if opts.individuals == "focus" else visible)]
            if not types:
                continue
            a = alias(ind.iri, ind.name, "I")
            out.append(f'object "{_q(_display(ind.label, ind.name, opts.name_style))}" as {a}')
            for t in types:
                out.append(f"{a} ..> {alias(t, model.classes[t].name)} : <<instanceOf>>")
                used.add("instance")

    out.append("")
    for iri in sorted(visible, key=lambda i: model.classes[i].name):
        k = model.classes[iri]
        texts = []
        if k.comment and (opts.notes == "all" or (opts.notes == "focus" and iri in opts.focus)):
            texts.append(k.comment)
        if iri in overlay.notes:
            texts.append(f"<b>{overlay.notes[iri]}</b>")
        if texts:
            used.add("note")
            body = [line for t in texts for line in _wrap(t, opts.note_width)]
            out.append(f"note right of {alias(iri, k.name)}")
            out += [f"  {_q(line)}" for line in body]
            out.append("end note")

    legend = []
    if opts.legend:
        rows = [(sym, desc) for key, sym, desc in NOTATION if key in used]
        if rows:
            legend.append("<b>기호</b>")
            legend += [f"{'<#fafafa,#cccccc>' if i == 0 else ''}| {sym} | {desc} |"
                       for i, (sym, desc) in enumerate(rows)]
    if diff:
        legend += [
            "<b>이전 버전 대비</b>",
            f"<back:{ADDED}>      </back> 추가된 클래스",
            f"<back:{CHANGED}>      </back> 변경된 클래스",
            f"<back:{REMOVED}>      </back> 삭제된 클래스 (점선)",
            f"<color:{ADDED_EDGE}><b>──▶</b></color> 추가된 관계",
            f"<color:{REMOVED_EDGE}>- - ▶</color> 삭제된 관계",
        ]
    elif source_colors:
        legend.append("<b>출처 (dcterms:source)</b>")
        legend += [f"<back:{c}>      </back> {s}" for s, c in source_colors.items()]
    if opts.standards:
        shown = sorted({model.classes[c].standard for c in visible if model.classes[c].standard})
        if shown:
            legend.append(f"<b>표준 온톨로지</b> (<back:{STANDARD_BG}> 회색 박스 </back>)")
            legend += [f"«{s}» {model.standards.get(s, s)}" for s in shown]
    if legend:
        out += ["", "legend bottom right", *legend, "endlegend"]

    out.append("@enduml")
    return "\n".join(out) + "\n"
