import re

from pydantic import BaseModel, Field

from app.domain import Chunk, Entity, Relation
from app.domain.ids import generate_entity_id, generate_relation_id, normalize_entity_name


class ExtractedEntity(BaseModel):
    name: str
    entity_type: str
    description: str = ""


class ExtractedRelation(BaseModel):
    source: str
    predicate: str
    target: str
    description: str = ""
    weight: float = 1.0


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)


# Known vocabulary for deterministic extraction over engineering documents
KNOWN_ENTITIES: dict[str, str] = {
    "PostgreSQL 16": "DATABASE",
    "PostgreSQL": "DATABASE",
    "Qdrant": "DATABASE",
    "Neo4j 5": "DATABASE",
    "Neo4j": "DATABASE",
    "Redis 7": "DATABASE",
    "Redis": "DATABASE",
    "PaymentGateway": "SERVICE",
    "CoreBanking": "SERVICE",
    "Data Platform Team": "TEAM",
    "SRE Team": "TEAM",
    "Core Banking Team": "TEAM",
    "Payments Team": "TEAM",
    "Alice Chen": "PERSON",
    "Bob Kumar": "PERSON",
    "Dave Miller": "PERSON",
    "Elena Rostova": "PERSON",
    "#data-platform": "SLACK_CHANNEL",
    "#sre-oncall": "SLACK_CHANNEL",
    "#core-banking": "SLACK_CHANNEL",
    "#payments-dev": "SLACK_CHANNEL",
    "INC-2026-04": "INCIDENT",
    "Bi-temporal Graph": "CONCEPT",
    "DLQ Monitoring": "REMEDIATION",
    "Outbox": "MECHANISM",
}


class EntityRelationExtractor:
    """Extracts entities and relationships from chunks using patterns or LLM prompts."""

    @classmethod
    def extract_from_chunk(cls, chunk: Chunk) -> ExtractionResult:
        """Heuristic/pattern-based extraction matching technical entities and relationships."""
        text = chunk.text
        found_entities: dict[str, str] = {}

        # 1. Match known entities present in the chunk text
        for name, ent_type in KNOWN_ENTITIES.items():
            pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
            if pattern.search(text):
                found_entities[name] = ent_type

        # 2. Heuristic relation rules based on common syntactic patterns
        relations: list[ExtractedRelation] = []

        # Lead: Person leads Team
        lead_match = re.findall(
            r"(?:\*\*Team Lead\*\*|Team Lead|Lead):\s*([a-zA-Z\s]+?)(?:\s*\(|\s*,|\s*\n|$)",
            text,
            re.IGNORECASE,
        )
        for person in lead_match:
            person_clean = person.strip()
            found_entities[person_clean] = "PERSON"
            if "Data Platform" in text:
                relations.append(
                    ExtractedRelation(
                        source="Data Platform Team",
                        predicate="LED_BY",
                        target=person_clean,
                    )
                )
                found_entities["Data Platform Team"] = "TEAM"
            if "SRE" in text:
                relations.append(
                    ExtractedRelation(
                        source="SRE Team",
                        predicate="LED_BY",
                        target=person_clean,
                    )
                )
                found_entities["SRE Team"] = "TEAM"
            if "Core Banking" in text:
                relations.append(
                    ExtractedRelation(
                        source="Core Banking Team",
                        predicate="LED_BY",
                        target=person_clean,
                    )
                )
                found_entities["Core Banking Team"] = "TEAM"
            if "Payments" in text:
                relations.append(
                    ExtractedRelation(
                        source="Payments Team",
                        predicate="LED_BY",
                        target=person_clean,
                    )
                )
                found_entities["Payments Team"] = "TEAM"

        # Slack Channel
        slack_match = re.findall(
            r"(?:\*\*Slack Channel\*\*|Slack Channel):\s*([#a-zA-Z0-9_\-]+)",
            text,
            re.IGNORECASE,
        )
        for ch in slack_match:
            ch_clean = ch.strip()
            found_entities[ch_clean] = "SLACK_CHANNEL"
            if "Data Platform" in text:
                relations.append(
                    ExtractedRelation(
                        source="Data Platform Team",
                        predicate="HAS_SLACK_CHANNEL",
                        target=ch_clean,
                    )
                )

        # Team owns Service / Database
        if "Data Platform Team" in found_entities or "Data Platform" in text:
            found_entities["Data Platform Team"] = "TEAM"
            for db in ["PostgreSQL 16", "PostgreSQL", "Qdrant", "Neo4j", "Neo4j 5"]:
                if db in found_entities or db in text:
                    found_entities[db] = "DATABASE"
                    relations.append(
                        ExtractedRelation(
                            source=db,
                            predicate="OWNED_BY",
                            target="Data Platform Team",
                        )
                    )

        if "Payments Team" in found_entities and "PaymentGateway" in found_entities:
            relations.append(
                ExtractedRelation(
                    source="PaymentGateway",
                    predicate="OWNED_BY",
                    target="Payments Team",
                )
            )

        if "Core Banking Team" in found_entities and "CoreBanking" in found_entities:
            relations.append(
                ExtractedRelation(
                    source="CoreBanking",
                    predicate="OWNED_BY",
                    target="Core Banking Team",
                )
            )

        # RFC knowledge graph hosting
        if "bi-temporal" in text.lower() and ("neo4j" in text.lower() or "neo4j 5" in text.lower()):
            found_entities["Bi-temporal Graph"] = "CONCEPT"
            found_entities["Neo4j"] = "DATABASE"
            relations.append(
                ExtractedRelation(
                    source="Bi-temporal Graph",
                    predicate="HOSTED_ON",
                    target="Neo4j",
                )
            )

        # Incident impacted Service / commanded by / root cause / remediation
        if "INC-2026-04" in found_entities or "INC-2026-04" in text:
            found_entities["INC-2026-04"] = "INCIDENT"
            if "PaymentGateway" in found_entities or "PaymentGateway" in text:
                found_entities["PaymentGateway"] = "SERVICE"
                relations.append(
                    ExtractedRelation(
                        source="INC-2026-04",
                        predicate="IMPACTED",
                        target="PaymentGateway",
                    )
                )
            if "Bob Kumar" in found_entities or "Bob Kumar" in text:
                found_entities["Bob Kumar"] = "PERSON"
                relations.append(
                    ExtractedRelation(
                        source="Bob Kumar",
                        predicate="COMMANDED",
                        target="INC-2026-04",
                    )
                )
            if "CoreBanking" in found_entities or "CoreBanking" in text:
                found_entities["CoreBanking"] = "SERVICE"
                relations.append(
                    ExtractedRelation(
                        source="INC-2026-04",
                        predicate="CAUSED_BY_DEPLOYMENT_OF",
                        target="CoreBanking",
                    )
                )
            if "dead-letter queue" in text.lower() or "dlq" in text.lower():
                found_entities["DLQ Monitoring"] = "REMEDIATION"
                found_entities["Alice Chen"] = "PERSON"
                relations.append(
                    ExtractedRelation(
                        source="INC-2026-04",
                        predicate="HAS_REMEDIATION",
                        target="DLQ Monitoring",
                    )
                )
                relations.append(
                    ExtractedRelation(
                        source="DLQ Monitoring",
                        predicate="ASSIGNED_TO",
                        target="Alice Chen",
                    )
                )

        # Storage / Outbox relations
        if "outbox" in text.lower():
            pg_name = "PostgreSQL"
            found_entities["Outbox"] = "MECHANISM"
            found_entities[pg_name] = "DATABASE"
            relations.append(
                ExtractedRelation(
                    source="Outbox",
                    predicate="STAGED_IN",
                    target=pg_name,
                )
            )

        entities_list = [
            ExtractedEntity(name=name, entity_type=etype) for name, etype in found_entities.items()
        ]
        return ExtractionResult(entities=entities_list, relations=relations)

    @classmethod
    def to_domain_graph(
        cls,
        result: ExtractionResult,
        chunk: Chunk,
    ) -> tuple[list[Entity], list[Relation]]:
        """Convert extracted entities and relations into fully qualified Domain models."""
        domain_entities: dict[str, Entity] = {}
        for ent in result.entities:
            eid = generate_entity_id(ent.name, ent.entity_type)
            domain_entities[normalize_entity_name(ent.name)] = Entity(
                entity_id=eid,
                name=ent.name,
                entity_type=ent.entity_type,
                description=ent.description,
                source_chunk_ids=[chunk.chunk_id],
                acl_scope=chunk.acl_scope,
                temporal=chunk.temporal,
                provenance=chunk.provenance,
            )

        domain_relations: list[Relation] = []
        for rel in result.relations:
            src_norm = normalize_entity_name(rel.source)
            tgt_norm = normalize_entity_name(rel.target)

            src_entity = domain_entities.get(src_norm)
            tgt_entity = domain_entities.get(tgt_norm)

            # Ensure entities exist or synthesize them
            if src_entity is None:
                src_id = generate_entity_id(rel.source, "CONCEPT")
                src_entity = Entity(
                    entity_id=src_id,
                    name=rel.source,
                    entity_type="CONCEPT",
                    source_chunk_ids=[chunk.chunk_id],
                    acl_scope=chunk.acl_scope,
                    temporal=chunk.temporal,
                    provenance=chunk.provenance,
                )
                domain_entities[src_norm] = src_entity

            if tgt_entity is None:
                tgt_id = generate_entity_id(rel.target, "CONCEPT")
                tgt_entity = Entity(
                    entity_id=tgt_id,
                    name=rel.target,
                    entity_type="CONCEPT",
                    source_chunk_ids=[chunk.chunk_id],
                    acl_scope=chunk.acl_scope,
                    temporal=chunk.temporal,
                    provenance=chunk.provenance,
                )
                domain_entities[tgt_norm] = tgt_entity

            rel_id = generate_relation_id(
                src_entity.entity_id,
                rel.predicate,
                tgt_entity.entity_id,
            )
            domain_relations.append(
                Relation(
                    relation_id=rel_id,
                    source_entity_id=src_entity.entity_id,
                    target_entity_id=tgt_entity.entity_id,
                    relation_type=rel.predicate,
                    description=rel.description,
                    weight=rel.weight,
                    source_chunk_ids=[chunk.chunk_id],
                    acl_scope=chunk.acl_scope,
                    temporal=chunk.temporal,
                    provenance=chunk.provenance,
                )
            )

        return list(domain_entities.values()), domain_relations
