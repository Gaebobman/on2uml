"""Recognise classes that come from standard (upper/reference) ontologies by namespace."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Standard:
    short: str  # shown as the «stereotype»
    title: str  # shown in the legend
    prefix: str


KNOWN: list[Standard] = [
    Standard("BFO", "Basic Formal Ontology", "http://purl.obolibrary.org/obo/BFO_"),
    Standard("RO", "OBO Relation Ontology", "http://purl.obolibrary.org/obo/RO_"),
    Standard("IAO", "Information Artifact Ontology", "http://purl.obolibrary.org/obo/IAO_"),
    Standard("OBI", "Ontology for Biomedical Investigations", "http://purl.obolibrary.org/obo/OBI_"),
    Standard("IOF", "Industrial Ontology Foundry", "https://spec.industrialontologies.org/ontology/"),
    Standard("CCO", "Common Core Ontologies", "http://www.ontologyrepository.com/CommonCoreOntologies/"),
    Standard("CCO", "Common Core Ontologies", "https://www.commoncoreontologies.org/"),
    Standard("schema", "schema.org", "https://schema.org/"),
    Standard("schema", "schema.org", "http://schema.org/"),
    Standard("PROV", "W3C PROV-O", "http://www.w3.org/ns/prov#"),
    Standard("SOSA", "W3C SOSA", "http://www.w3.org/ns/sosa/"),
    Standard("SSN", "W3C SSN", "http://www.w3.org/ns/ssn/"),
    Standard("Time", "W3C OWL-Time", "http://www.w3.org/2006/time#"),
    Standard("SKOS", "W3C SKOS", "http://www.w3.org/2004/02/skos/core#"),
    Standard("DCT", "DCMI Terms", "http://purl.org/dc/terms/"),
    Standard("FOAF", "FOAF", "http://xmlns.com/foaf/0.1/"),
    Standard("QUDT", "QUDT", "http://qudt.org/schema/qudt/"),
    Standard("gist", "gist", "https://w3id.org/semanticarts/ns/ontology/gist/"),
]


class Catalog:
    def __init__(self, extra: dict[str, str] | None = None):
        """extra: namespace prefix -> name (user/company standards), checked before KNOWN."""
        user = [Standard(name, name, prefix) for prefix, name in (extra or {}).items()]
        # Longest prefix wins, so a specific sub-namespace can override a broad one.
        self._table = sorted(user + KNOWN, key=lambda s: -len(s.prefix))

    def of(self, iri: str) -> Standard | None:
        for s in self._table:
            if iri.startswith(s.prefix):
                return s
        return None


def parse_namespace_args(values: list[str]) -> dict[str, str]:
    """CLI form PREFIX=NAME."""
    out = {}
    for v in values:
        prefix, sep, name = v.rpartition("=")
        if not sep or not prefix or not name:
            raise ValueError(f"--namespace expects PREFIX=NAME, got '{v}'")
        out[prefix] = name
    return out
