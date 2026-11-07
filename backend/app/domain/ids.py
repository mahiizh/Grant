import hashlib
import re


def normalize_entity_name(name: str) -> str:
    """Normalize entity names by lowercasing, stripping extra whitespace and punctuation."""
    cleaned = re.sub(r"[^\w\s-]", "", name.strip().lower())
    return re.sub(r"\s+", "_", cleaned)


def generate_doc_id(source_identifier: str, version: int = 1) -> str:
    """Generate deterministic document ID based on source URI or title and version."""
    payload = f"{source_identifier.strip()}::v{version}".encode()
    digest = hashlib.sha256(payload).hexdigest()[:12]
    # Clean prefix for readability
    clean_prefix = re.sub(r"[^\w-]", "_", source_identifier.strip().lower())[:16].strip("_")
    return f"doc_{clean_prefix}_{digest}" if clean_prefix else f"doc_{digest}"


def generate_chunk_id(doc_id: str, chunk_index: int, text_content: str) -> str:
    """Generate deterministic chunk ID bound to its parent doc, position, and text hash."""
    content_hash = hashlib.sha256(text_content.strip().encode("utf-8")).hexdigest()[:10]
    return f"chk_{doc_id}_{chunk_index:04d}_{content_hash}"


def generate_entity_id(name: str, entity_type: str) -> str:
    """Generate deterministic entity ID based on normalized entity name and type."""
    normalized_name = normalize_entity_name(name)
    type_prefix = re.sub(r"[^\w-]", "", entity_type.strip().lower())[:8]
    digest = hashlib.sha256(f"{type_prefix}:{normalized_name}".encode()).hexdigest()[:10]
    return f"ent_{type_prefix}_{normalized_name[:20]}_{digest}".strip("_")


def generate_relation_id(
    source_entity_id: str,
    relation_type: str,
    target_entity_id: str,
) -> str:
    """Generate deterministic relation ID between source, relation predicate, and target."""
    predicate = re.sub(r"[^\w-]", "", relation_type.strip().upper())
    payload = f"{source_entity_id}->{predicate}->{target_entity_id}".encode()
    digest = hashlib.sha256(payload).hexdigest()[:12]
    return f"rel_{predicate.lower()}_{digest}"
