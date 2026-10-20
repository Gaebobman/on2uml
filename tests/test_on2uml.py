from pathlib import Path

import pytest
from rdflib import Graph, Literal, RDFS, URIRef

from on2uml.diff import compare
from on2uml.model import load
from on2uml.puml import Options, build
from on2uml.cli import main
from on2uml.view import collapse, select

EXAMPLE = Path(__file__).parent.parent / "examples" / "vehicle.ttl"
AXIOMS = Path(__file__).parent / "data" / "axioms.ttl"
NS = "http://example.org/vehicle#"
AX = "http://example.org/ax#"


@pytest.fixture
def model():
    return load(EXAMPLE)


def test_mapping(model):
    vehicle = model.classes[NS + "Vehicle"]
    assert vehicle.label == "차량"
    assert vehicle.parents == [NS + "Thing"]
    assert [a.name for a in vehicle.attributes] == ["modelYear"]
    assert vehicle.source == "core"
    assert {(a.name, a.range) for a in model.associations} == {
        ("manufacturedBy", NS + "Manufacturer"),
        ("hasEngineType", NS + "EngineType"),
    }
    assert set(model.individuals) == {NS + "Diesel", NS + "Electric"}


def test_resolve_by_name_and_label(model):
    assert model.resolve("Truck") == NS + "Truck"
    assert model.resolve("트럭") == NS + "Truck"
    assert model.resolve("nope") is None


def test_focus_depth(model):
    one = select(model, focus=["Truck"], depth=1, inherited=False)
    assert one == {NS + "Truck", NS + "Vehicle"}
    # inherited associations pull in their far ends at the same depth
    assert select(model, focus=["Truck"], depth=1) == one | {NS + "Manufacturer", NS + "EngineType"}
    two = select(model, focus=["Truck"], depth=2)
    assert {NS + "Manufacturer", NS + "Car", NS + "Thing"} <= two


def test_subtree_and_exclude(model):
    chosen = select(model, subtree=["Vehicle"], exclude=["Bus"])
    assert chosen == {NS + c for c in ("Vehicle", "Car", "Truck", "Motorcycle")}


def test_unknown_focus_raises(model):
    with pytest.raises(ValueError):
        select(model, focus=["Spaceship"])


def test_collapse_keeps_classes_with_attributes(model):
    reduced, folded = collapse(model, set(model.classes), threshold=2)
    # Truck has an attribute, so only the three plain leaves fold
    assert folded == {NS + "Vehicle": ["버스", "승용차", "오토바이"]}
    assert NS + "Truck" in reduced and NS + "Car" not in reduced


def test_diff(tmp_path, model):
    g = Graph().parse(EXAMPLE, format="turtle")
    g.remove((URIRef(NS + "Bus"), None, None))
    g.set((URIRef(NS + "Car"), RDFS.label, Literal("자동차")))
    g.remove((URIRef(NS + "hasEngineType"), None, None))
    old_path = tmp_path / "old.ttl"
    g.serialize(old_path, format="turtle")

    d = compare(load(old_path), model)
    assert d.added == {NS + "Bus"}
    assert d.changed == {NS + "Car"}
    assert d.removed == {}
    assert d.assoc_added == {(NS + "hasEngineType", NS + "Vehicle", NS + "EngineType", "property")}


def test_build_puml(model):
    opts = Options(focus={NS + "Vehicle"}, individuals=True)
    src = build(model, set(model.classes), opts)
    assert src.startswith("@startuml") and src.rstrip().endswith("@enduml")
    assert "C_Vehicle <|-- C_Truck" in src
    assert "C_Vehicle --> C_Manufacturer" in src
    assert "적재량" in src
    assert "note right of C_Vehicle" in src
    assert "note right of C_Manufacturer" not in src  # notes only for focus by default
    assert "I_Diesel ..> C_EngineType" in src


def test_individuals_focus_only(model):
    # "focus" keeps a neighbour class's individuals out of the diagram
    src = build(model, set(model.classes), Options(focus={NS + "Vehicle"}, individuals="focus"))
    assert "I_Diesel" not in src and "C_Vehicle --> C_EngineType" in src
    src = build(model, set(model.classes), Options(focus={NS + "EngineType"}, individuals="focus"))
    assert "I_Diesel ..> C_EngineType" in src


# --- inherited associations / attributes -------------------------------------

def test_focus_reaches_inherited_association_ends(model):
    chosen = select(model, focus=["Truck"], depth=1, exclude=["Vehicle"])
    assert chosen == {NS + "Truck", NS + "Manufacturer", NS + "EngineType"}
    assert select(model, focus=["Truck"], depth=1, exclude=["Vehicle"], inherited=False) == {NS + "Truck"}


def test_inherited_replayed_when_ancestor_hidden(model):
    chosen = select(model, focus=["Truck"], depth=1, exclude=["Vehicle"])
    src = build(model, chosen, Options(focus={NS + "Truck"}))
    assert "C_Truck -[#8a8fb5,dashed]-> C_Manufacturer" in src
    assert "차량에서 상속" in src  # inherited modelYear section + edge label
    assert "그림 밖 상위 클래스에서 물려받은 관계" in src  # legend
    assert "</color></color>" not in src and "<color:#777777><color" not in src  # no nested colors


def test_inherited_not_duplicated_when_ancestor_visible(model):
    chosen = select(model, focus=["Truck"], depth=1)
    src = build(model, chosen, Options(focus={NS + "Truck"}))
    assert "C_Vehicle --> C_Manufacturer" in src
    assert "dashed]-> C_Manufacturer" not in src
    assert "에서 상속" not in src


# --- blank-node axioms --------------------------------------------------------

@pytest.fixture
def axioms():
    return load(AXIOMS)


def _edges(m, domain):
    return {(a.name, a.range.split("#")[1], a.mult, a.qualifier) for a in m.associations if a.domain == AX + domain}


def test_restrictions_become_edges_with_multiplicity(axioms):
    edges = _edges(axioms, "Order")
    assert ("hasLine", "OrderLine", "1..*", None) in edges
    assert ("placedBy", "Customer", None, "only") in edges
    assert ("shipTo", "Address", "0..2", None) in edges


def test_union_range_expands(axioms):
    edges = _edges(axioms, "Order")
    assert ("owner", "Customer", None, None) in edges and ("owner", "Company", None, None) in edges


def test_data_restrictions_become_attributes(axioms):
    attrs = {(a.name, a.range, a.mult, a.value) for a in axioms.classes[AX + "Order"].attributes}
    assert ("status", None, None, '"open"') in attrs
    assert ("total", "decimal", "1..*", None) in attrs


def test_intersection_equivalence(axioms):
    prio = axioms.classes[AX + "PriorityOrder"]
    assert prio.parents == [AX + "Order"]
    assert ("hasLine", "OrderLine", "5..*", None) in _edges(axioms, "PriorityOrder")
    assert axioms.classes[AX + "Client"].equivalents == [AX + "Customer"]


def test_unsupported_axiom_warns(axioms):
    assert any("complementOf" in w for w in axioms.warnings)


def test_restriction_merges_with_declared_edge(axioms):
    src = build(axioms, set(axioms.classes), Options())
    hasline = [l for l in src.splitlines() if l.startswith("C_Order ") and "hasLine" in l]
    assert hasline == ['C_Order --> "1..*" C_OrderLine : hasLine']
    assert "C_Client .. C_Customer : ≡" in src


# --- views.yaml ---------------------------------------------------------------

def test_config_renders_every_view(tmp_path):
    cfg = tmp_path / "views.yaml"
    cfg.write_text(f"""
ontology: {EXAMPLE}
format: puml
output_dir: out
defaults:
  exclude: [Thing]
views:
  - name: all
    notes: none
  - name: truck
    focus: Truck
    depth: 1
""", encoding="utf-8")
    assert main(["--config", str(cfg)]) == 0
    assert "C_Truck" in (tmp_path / "out" / "truck.puml").read_text(encoding="utf-8")
    assert "C_Thing" not in (tmp_path / "out" / "all.puml").read_text(encoding="utf-8")
    assert main(["--config", str(cfg), "--only", "nope"]) == 2


def test_config_rejects_unknown_keys(tmp_path):
    cfg = tmp_path / "views.yaml"
    cfg.write_text(f"ontology: {EXAMPLE}\nviews:\n  - name: a\n    focuss: Truck\n", encoding="utf-8")
    with pytest.raises(ValueError, match="focuss"):
        from on2uml.config import load_config
        load_config(cfg)


# --- standard ontologies ------------------------------------------------------

STD = Path(__file__).parent / "data" / "standards.ttl"
BFO_ME = "http://purl.obolibrary.org/obo/BFO_0000040"
IOF_POE = "https://spec.industrialontologies.org/ontology/core/Core/PieceOfEquipment"


def test_known_standards_detected():
    m = load(STD)
    assert m.classes[BFO_ME].standard == "BFO"
    assert m.classes[IOF_POE].standard == "IOF"
    assert m.classes["http://example.org/plant#Pump"].standard is None
    assert m.classes["https://std.example.com/core#Vessel"].standard is None  # unknown until configured
    assert m.standards == {"BFO": "Basic Formal Ontology", "IOF": "Industrial Ontology Foundry"}


def test_user_namespaces_and_longest_prefix():
    m = load(STD, namespaces={
        "https://std.example.com/core#": "CORP",
        "https://spec.industrialontologies.org/ontology/core/": "IOF-Core",
    })
    assert m.classes["https://std.example.com/core#Vessel"].standard == "CORP"
    assert m.classes[IOF_POE].standard == "IOF-Core"


def test_stereotypes_and_legend():
    m = load(STD)
    src = build(m, set(m.classes), Options())
    assert 'as C_PieceOfEquipment <<IOF>>' in src
    assert 'as C_BFO_0000040 <<BFO>>' in src
    assert "«IOF» Industrial Ontology Foundry" in src
    off = build(m, set(m.classes), Options(standards=False))
    assert "<<IOF>>" not in off and "표준 온톨로지" not in off


def test_namespace_arg_parsing():
    from on2uml.standards import parse_namespace_args
    assert parse_namespace_args(["https://x.org/a#=X"]) == {"https://x.org/a#": "X"}
    with pytest.raises(ValueError):
        parse_namespace_args(["no-equals"])


# --- per-class diagrams + change tracking -------------------------------------

def _fake_render(paths, fmt, jar=None):
    for p in paths:
        p.with_suffix(f".{fmt}").write_bytes(b"img")


def test_per_class_tracks_changes(tmp_path, monkeypatch):
    import json
    from on2uml import perclass
    from on2uml.config import load_config

    monkeypatch.setattr(perclass, "render_many", _fake_render)
    ttl = tmp_path / "onto.ttl"
    ttl.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    cfg_path = tmp_path / "views.yaml"
    cfg_path.write_text("ontology: onto.ttl\nper_class:\n  classes: all\n  output_dir: cls\n", encoding="utf-8")

    def run_once():
        cfg = load_config(cfg_path)
        return perclass.run(cfg.per_class, load(cfg.ontology), ontology_name="onto.ttl")

    first = run_once()
    assert len(first.added) == 8 and not first.changed and not first.removed
    out = tmp_path / "cls"
    assert (out / "Truck.png").exists() and (out / "Truck.puml").exists()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["classes"]["Truck"]["iri"] == NS + "Truck"

    again = run_once()  # deterministic output: nothing to redo
    assert again.unchanged == 8 and not (again.added or again.changed or again.removed)
    assert "변경 없음" in (out / "index.md").read_text(encoding="utf-8")

    g = Graph().parse(ttl, format="turtle")
    g.set((URIRef(NS + "Truck"), RDFS.label, Literal("화물차")))
    g.remove((URIRef(NS + "Bus"), None, None))
    g.serialize(ttl, format="turtle")
    third = run_once()
    assert "Truck" in third.changed and "Vehicle" in third.changed  # Vehicle's card shows Truck
    assert third.removed == ["Bus"]
    assert not (out / "Bus.png").exists() and not (out / "Bus.puml").exists()
    index = (out / "index.md").read_text(encoding="utf-8")
    assert "**삭제 1**: Bus" in index and "| 화물차 | Truck |" in index


def test_per_class_domain_only_and_unknown_key(tmp_path, monkeypatch):
    from on2uml import perclass
    from on2uml.config import load_config

    monkeypatch.setattr(perclass, "render_many", _fake_render)
    cfg_path = tmp_path / "views.yaml"
    cfg_path.write_text(f"ontology: {STD}\nper_class:\n  classes: domain\n  output_dir: cls\n", encoding="utf-8")
    cfg = load_config(cfg_path)
    rep = perclass.run(cfg.per_class, load(cfg.ontology))
    assert sorted(rep.added) == ["Pump", "Tank", "Vessel"]  # BFO/IOF classes skipped

    cfg_path.write_text(f"ontology: {STD}\nper_class:\n  focus: Pump\n", encoding="utf-8")
    with pytest.raises(ValueError, match="focus"):
        load_config(cfg_path)


def test_focus_survives_exclude(model):
    assert NS + "Thing" in select(model, focus=["Thing"], exclude=["Thing"])


def test_legend_lists_only_drawn_notation(model, axioms):
    src = build(model, select(model, focus=["Truck"]), Options(focus={NS + "Truck"}))
    assert "legend bottom right" in src
    assert "상속: 자식은 부모의 한 종류" in src
    assert "끝의 숫자" not in src and "«only»" not in src and "equivalentClass" not in src

    src = build(axioms, set(axioms.classes), Options())
    for text in ("끝의 숫자", "allValuesFrom", "equivalentClass", "고정값"):
        assert text in src

    off = build(model, select(model, focus=["Truck"]), Options(focus={NS + "Truck"}, legend=False))
    assert "endlegend" not in off


def test_config_rejects_bad_individuals(tmp_path):
    cfg = tmp_path / "views.yaml"
    cfg.write_text(f"ontology: {EXAMPLE}\nviews:\n  - name: a\n    individuals: some\n", encoding="utf-8")
    from on2uml.config import load_config
    with pytest.raises(ValueError, match="individuals"):
        load_config(cfg)


def test_long_overlay_note_bold_per_line(model):
    from on2uml.overlay import Overlay
    ov = Overlay(notes={NS + "Vehicle": "아주 긴 설명 메모가 여러 줄로 접혀도 굵은 글씨 표시가 줄마다 닫혀야 한다"})
    src = build(model, set(model.classes), Options(notes="none"), overlay=ov)
    lines = [l.strip() for l in src.splitlines() if "<b>" in l and "기호" not in l]
    assert len(lines) > 1 and all(l.startswith("<b>") and l.endswith("</b>") for l in lines)


def test_plantuml_runs_headless(monkeypatch):
    from on2uml import render

    monkeypatch.setenv("PLANTUML_JAR", "/x/plantuml.jar")
    assert "-Djava.awt.headless=true" in render._command(None)
    monkeypatch.delenv("JAVA_TOOL_OPTIONS", raising=False)
    assert render._env()["JAVA_TOOL_OPTIONS"] == "-Djava.awt.headless=true"
    monkeypatch.setenv("JAVA_TOOL_OPTIONS", "-Xmx2g")
    assert render._env()["JAVA_TOOL_OPTIONS"] == "-Xmx2g -Djava.awt.headless=true"
    monkeypatch.setenv("JAVA_TOOL_OPTIONS", "-Djava.awt.headless=false")
    assert render._env()["JAVA_TOOL_OPTIONS"] == "-Djava.awt.headless=false"


def test_individuals_hide(model):
    from on2uml.model import Individual
    model.individuals[NS + "Hyundai"] = Individual(NS + "Hyundai", "Hyundai", None, [NS + "Manufacturer"])
    hide = {NS + "EngineType"}
    # true + hide: every drawn class's individuals except the hidden class's
    src = build(model, set(model.classes), Options(individuals=True, individuals_hide=hide))
    assert "I_Hyundai ..> C_Manufacturer" in src and "I_Diesel" not in src
    # focus + hide: hide wins even for a focus class
    src = build(model, set(model.classes), Options(focus={NS + "EngineType"}, individuals="focus", individuals_hide=hide))
    assert "I_Diesel" not in src and "I_Hyundai" not in src
    # default: nothing hidden
    src = build(model, set(model.classes), Options(individuals=True))
    assert "I_Diesel ..> C_EngineType" in src and "I_Hyundai" in src


def test_individuals_hide_config_and_cli(tmp_path):
    from on2uml.spec import ViewSpec, build_source
    model = load(EXAMPLE)
    spec = ViewSpec.from_dict({"output": "x.puml", "individuals": True, "individuals_hide": "엔진 형식"}, "t")
    assert spec.individuals_hide == ["엔진 형식"]
    src, _, _ = build_source(spec, model)
    assert "I_Diesel" not in src
    with pytest.raises(ValueError, match="individuals_hide"):
        build_source(ViewSpec(output="x.puml", individuals=True, individuals_hide=["Nope"]), model)
    out = tmp_path / "v.puml"
    assert main([str(EXAMPLE), "-o", str(out), "--individuals", "--individuals-hide", "EngineType"]) == 0
    assert "I_Diesel" not in out.read_text(encoding="utf-8")
