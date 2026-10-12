"""Load an OWL ontology into a small UML-oriented model.

Mapping:
  owl:Class              -> class box
  rdfs:subClassOf        -> generalization (inheritance arrow)
  owl:equivalentClass    -> dashed '≡' link (named classes)
  owl:DatatypeProperty   -> attribute line inside each rdfs:domain class
  owl:ObjectProperty     -> association from each rdfs:domain to each rdfs:range
  owl:NamedIndividual    -> object box linked to its rdf:type classes
  rdfs:comment / skos:definition -> note text
  class IRI in a known standard namespace (BFO, IOF, ...) -> «stereotype» (see standards.py)

Anonymous class expressions:
  subClassOf/equivalentClass [owl:Restriction]
      object filler   -> association with multiplicity (some 1..*, only «only», min n..*, max 0..n, exact n)
      data filler     -> attribute line with multiplicity
      owl:hasValue    -> attribute line 'p = value'
  owl:intersectionOf -> each named member is a parent, each restriction is handled as above
  owl:unionOf in rdfs:domain / rdfs:range / filler -> expanded to one edge per member
  anything else (complementOf, oneOf, nested expressions) -> warning, not drawn
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

from .standards import Catalog

DATATYPE_NAMESPACES = (str(XSD), str(RDF), str(RDFS) + "Literal")


def local_name(iri: str) -> str:
    for sep in ("#", "/"):
        if sep in iri:
            tail = iri.rsplit(sep, 1)[1]
            if tail:
                return tail
    return iri


@dataclass
class Attribute:
    iri: str
    name: str
    label: str | None
    range: str | None
    mult: str | None = None  # e.g. "1..*" from a restriction
    value: str | None = None  # owl:hasValue


@dataclass
class Klass:
    iri: str
    name: str
    label: str | None
    comment: str | None
    parents: list[str] = field(default_factory=list)
    equivalents: list[str] = field(default_factory=list)
    attributes: list[Attribute] = field(default_factory=list)
    source: str | None = None
    standard: str | None = None  # short name of the standard ontology the IRI belongs to, e.g. "BFO"

    def signature(self) -> tuple:
        """Everything that counts as a 'change' when comparing versions."""
        return (
            self.label,
            self.comment,
            tuple(sorted(self.parents)),
            tuple(sorted(self.equivalents)),
            tuple(sorted((a.iri, a.label, a.range, a.mult, a.value) for a in self.attributes)),
        )


@dataclass
class Association:
    iri: str
    name: str
    label: str | None
    domain: str
    range: str
    kind: str = "property"  # property (rdfs:domain/range) | restriction
    mult: str | None = None  # multiplicity at the range end
    qualifier: str | None = None  # e.g. "only"

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.iri, self.domain, self.range, self.kind)


@dataclass
class Individual:
    iri: str
    name: str
    label: str | None
    types: list[str]


@dataclass
class Model:
    classes: dict[str, Klass]
    associations: list[Association]
    individuals: dict[str, Individual]
    warnings: list[str] = field(default_factory=list)
    standards: dict[str, str] = field(default_factory=dict)  # short -> title, for those present

    def resolve(self, ref: str) -> str | None:
        """Find a class or individual IRI by full IRI, local name, or label."""
        pools = (self.classes, self.individuals)
        for pool in pools:
            if ref in pool:
                return ref
        for pool in pools:
            for iri, ent in pool.items():
                if ent.name == ref or ent.label == ref:
                    return iri
        return None

    def ancestors(self, iri: str) -> list[str]:
        """Strict ancestors, nearest first (breadth-first), cycle-safe."""
        out: list[str] = []
        frontier = list(self.classes[iri].parents) if iri in self.classes else []
        while frontier:
            nxt = []
            for p in frontier:
                if p in out or p == iri:
                    continue
                out.append(p)
                if p in self.classes:
                    nxt.extend(self.classes[p].parents)
            frontier = nxt
        return out


def _pick_literal(graph: Graph, subject, preds, lang: str | None) -> str | None:
    """Prefer the requested language, then untagged, then anything."""
    values: list[Literal] = [
        o for p in preds for o in graph.objects(subject, p) if isinstance(o, Literal)
    ]
    if not values:
        return None
    for want in (lang, None):
        for v in values:
            if v.language == want:
                return str(v)
    return str(values[0])


_CARDINALITY = [
    (OWL.cardinality, "{n}"),
    (OWL.qualifiedCardinality, "{n}"),
    (OWL.minCardinality, "{n}..*"),
    (OWL.minQualifiedCardinality, "{n}..*"),
    (OWL.maxCardinality, "0..{n}"),
    (OWL.maxQualifiedCardinality, "0..{n}"),
]


class _Loader:
    def __init__(self, graph: Graph, lang: str | None, catalog: Catalog):
        self.g = graph
        self.lang = lang
        self.catalog = catalog
        self.warnings: list[str] = []
        self.classes: dict[str, Klass] = {}
        self.associations: list[Association] = []
        self.standards: dict[str, str] = {}

    def label(self, s) -> str | None:
        return _pick_literal(self.g, s, [RDFS.label], self.lang)

    def comment(self, s) -> str | None:
        return _pick_literal(self.g, s, [RDFS.comment, SKOS.definition], self.lang)

    def warn(self, subject, msg: str) -> None:
        self.warnings.append(f"{local_name(str(subject))}: {msg}")

    def named_members(self, node, where: str, subject) -> list[str]:
        """A class expression usable as an edge end: a named class or a union of them."""
        if isinstance(node, URIRef):
            return [str(node)]
        union = self.g.value(node, OWL.unionOf)
        if union is not None:
            out = []
            for m in self.g.items(union):
                out.extend(self.named_members(m, where, subject))
            return out
        self.warn(subject, f"{where} uses an anonymous expression other than owl:unionOf; not drawn")
        return []

    def is_datatype(self, node) -> bool:
        return isinstance(node, URIRef) and (
            str(node).startswith(DATATYPE_NAMESPACES) or (node, RDF.type, RDFS.Datatype) in self.g
        )

    def is_data_property(self, prop) -> bool:
        return (prop, RDF.type, OWL.DatatypeProperty) in self.g

    def add_restriction(self, cls: Klass, node) -> None:
        g = self.g
        prop = g.value(node, OWL.onProperty)
        if not isinstance(prop, URIRef):
            self.warn(cls.iri, "restriction without a named owl:onProperty; not drawn")
            return
        pname, plabel = local_name(str(prop)), self.label(prop)

        def attribute(range_=None, mult=None, value=None):
            cls.attributes.append(
                Attribute(iri=str(prop), name=pname, label=plabel, range=range_, mult=mult, value=value)
            )

        def associate(filler, mult=None, qualifier=None):
            for target in self.named_members(filler, "restriction filler", cls.iri):
                self.associations.append(
                    Association(iri=str(prop), name=pname, label=plabel, domain=cls.iri, range=target,
                                kind="restriction", mult=mult, qualifier=qualifier)
                )

        def handle(filler, mult=None, qualifier=None):
            if filler is None:
                # Unqualified cardinality: fall back to the property's declared range.
                ranges = [r for r in g.objects(prop, RDFS.range)]
                if self.is_data_property(prop) or not ranges:
                    attribute(local_name(str(ranges[0])) if ranges and isinstance(ranges[0], URIRef) else None, mult)
                else:
                    for r in ranges:
                        associate(r, mult, qualifier)
            elif self.is_datatype(filler) or self.is_data_property(prop):
                rng = local_name(str(filler)) if isinstance(filler, URIRef) else None
                attribute(rng + (" «only»" if qualifier == "only" and rng else "") if rng else None, mult)
            else:
                associate(filler, mult, qualifier)

        if (v := g.value(node, OWL.someValuesFrom)) is not None:
            handle(v, mult="1..*")
        elif (v := g.value(node, OWL.allValuesFrom)) is not None:
            handle(v, qualifier="only")
        elif (v := g.value(node, OWL.hasValue)) is not None:
            shown = self.label(v) or local_name(str(v)) if isinstance(v, URIRef) else f'"{v}"'
            attribute(value=shown)
        else:
            for pred, fmt in _CARDINALITY:
                n = g.value(node, pred)
                if n is not None:
                    filler = g.value(node, OWL.onClass) or g.value(node, OWL.onDataRange)
                    handle(filler, mult=fmt.format(n=int(n)))
                    return
            self.warn(cls.iri, f"restriction on {pname} has no supported constraint; not drawn")

    def add_expression(self, cls: Klass, node, rel: str) -> None:
        """A subClassOf / equivalentClass object."""
        g = self.g
        if isinstance(node, URIRef):
            (cls.parents if rel == "subClassOf" else cls.equivalents).append(str(node))
        elif (node, RDF.type, OWL.Restriction) in g or g.value(node, OWL.onProperty) is not None:
            self.add_restriction(cls, node)
        elif (inter := g.value(node, OWL.intersectionOf)) is not None:
            for m in g.items(inter):
                if isinstance(m, URIRef):
                    cls.parents.append(str(m))
                else:
                    self.add_expression(cls, m, "subClassOf")
        else:
            kind = next((local_name(str(p)) for p in (OWL.unionOf, OWL.complementOf, OWL.oneOf)
                         if g.value(node, p) is not None), "anonymous class")
            self.warn(cls.iri, f"{rel} {kind} is not drawn yet")

    def load(self) -> Model:
        g = self.g
        for s in g.subjects(RDF.type, OWL.Class):
            if not isinstance(s, URIRef):
                continue
            iri = str(s)
            src = g.value(s, DCTERMS.source)
            std = self.catalog.of(iri)
            self.classes[iri] = Klass(
                iri=iri,
                name=local_name(iri),
                label=self.label(s),
                comment=self.comment(s),
                source=str(src).rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1] if src is not None else None,
                standard=std.short if std else None,
            )
            if std:
                self.standards.setdefault(std.short, std.title)
        for iri, cls in self.classes.items():
            s = URIRef(iri)
            for o in g.objects(s, RDFS.subClassOf):
                self.add_expression(cls, o, "subClassOf")
            for o in g.objects(s, OWL.equivalentClass):
                self.add_expression(cls, o, "equivalentClass")
            cls.parents = sorted(set(cls.parents))
            cls.equivalents = sorted(set(cls.equivalents))

        for p in g.subjects(RDF.type, OWL.DatatypeProperty):
            ranges = [local_name(str(r)) for r in g.objects(p, RDFS.range) if isinstance(r, URIRef)]
            for d in g.objects(p, RDFS.domain):
                for dom in self.named_members(d, "rdfs:domain", p):
                    if dom not in self.classes:
                        self.warn(p, f"domain {local_name(dom)} is not a declared class")
                        continue
                    self.classes[dom].attributes.append(
                        Attribute(iri=str(p), name=local_name(str(p)), label=self.label(p),
                                  range=ranges[0] if ranges else None)
                    )
        for k in self.classes.values():
            k.attributes.sort(key=lambda a: (a.name, a.mult or "", a.value or ""))

        for p in g.subjects(RDF.type, OWL.ObjectProperty):
            doms = [m for d in g.objects(p, RDFS.domain) for m in self.named_members(d, "rdfs:domain", p)]
            rngs = [m for r in g.objects(p, RDFS.range) for m in self.named_members(r, "rdfs:range", p)]
            for dom in doms:
                for rng in rngs:
                    self.associations.append(
                        Association(iri=str(p), name=local_name(str(p)), label=self.label(p), domain=dom, range=rng)
                    )
        self.associations.sort(key=lambda a: a.key)

        individuals: dict[str, Individual] = {}
        for s in g.subjects(RDF.type, OWL.NamedIndividual):
            if not isinstance(s, URIRef):
                continue
            types = sorted(str(t) for t in g.objects(s, RDF.type) if str(t) in self.classes)
            individuals[str(s)] = Individual(iri=str(s), name=local_name(str(s)), label=self.label(s), types=types)

        return Model(classes=self.classes, associations=self.associations, individuals=individuals,
                     warnings=sorted(set(self.warnings)), standards=self.standards)


def load(path: str | Path, lang: str | None = "ko", namespaces: dict[str, str] | None = None) -> Model:
    """namespaces: extra PREFIX -> NAME pairs marking in-house/other standard ontologies."""
    graph = Graph().parse(str(path), format="turtle")
    return _Loader(graph, lang, Catalog(namespaces)).load()
