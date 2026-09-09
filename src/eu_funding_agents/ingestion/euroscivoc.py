from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from rdflib import RDF, Graph, Literal, URIRef
from rdflib.namespace import OWL, SKOS

SKOSXL = "http://www.w3.org/2008/05/skos-xl#"
EUROSCIVOC_VERSION = "1.5"
EUROSCIVOC_TTL_URL = "https://data.europa.eu/api/hub/store/data/679b952682f7752a299f855a"


class EuroSciVocError(ValueError):
    """Raised when a EuroSciVoc snapshot does not satisfy the expected SKOS shape."""


@dataclass(frozen=True)
class EuroSciVocConceptRecord:
    uri: str
    notation: str | None
    version: str | None
    deprecated: bool
    preferred_labels: dict[str, str]
    alternative_labels: dict[str, list[str]]
    broader_uris: tuple[str, ...]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _label_map(graph: Graph, concept: URIRef, predicate: URIRef) -> dict[str, list[str]]:
    labels: dict[str, list[str]] = {}
    literal_form = URIRef(f"{SKOSXL}literalForm")
    for label_node in graph.objects(concept, predicate):
        literal = graph.value(label_node, literal_form)
        if not isinstance(literal, Literal):
            continue
        language = literal.language or "und"
        labels.setdefault(language, []).append(str(literal))
    return {language: sorted(set(values)) for language, values in sorted(labels.items())}


def parse_euroscivoc(path: Path) -> list[EuroSciVocConceptRecord]:
    if not path.is_file():
        raise EuroSciVocError(f"EuroSciVoc snapshot does not exist: {path}")

    graph = Graph()
    try:
        graph.parse(path, format="turtle")
    except Exception as exc:
        raise EuroSciVocError(f"Invalid EuroSciVoc Turtle snapshot: {path}") from exc

    concept_nodes = sorted(
        (node for node in graph.subjects(RDF.type, SKOS.Concept) if isinstance(node, URIRef)),
        key=str,
    )
    if not concept_nodes:
        raise EuroSciVocError("EuroSciVoc snapshot contains no skos:Concept resources")

    concept_uris = {str(node) for node in concept_nodes}
    records: list[EuroSciVocConceptRecord] = []
    for concept in concept_nodes:
        preferred = _label_map(graph, concept, URIRef(f"{SKOSXL}prefLabel"))
        if not preferred:
            raise EuroSciVocError(f"Concept has no SKOS-XL preferred label: {concept}")
        alternative = _label_map(graph, concept, URIRef(f"{SKOSXL}altLabel"))
        notation = graph.value(concept, SKOS.notation)
        version = graph.value(concept, OWL.versionInfo)
        deprecated = graph.value(concept, OWL.deprecated)
        broader = tuple(
            sorted(
                str(parent)
                for parent in graph.objects(concept, SKOS.broader)
                if isinstance(parent, URIRef) and str(parent) in concept_uris
            )
        )
        records.append(
            EuroSciVocConceptRecord(
                uri=str(concept),
                notation=str(notation) if notation is not None else None,
                version=str(version) if version is not None else None,
                deprecated=str(deprecated).casefold() == "true",
                preferred_labels={key: values[0] for key, values in preferred.items()},
                alternative_labels=alternative,
                broader_uris=broader,
            )
        )
    return records
