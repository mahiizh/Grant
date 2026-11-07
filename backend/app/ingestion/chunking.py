from datetime import UTC, datetime

from app.core.acl import ACLScope
from app.domain import Chunk, Provenance, TemporalBounds
from app.domain.ids import generate_chunk_id
from app.ingestion.parse import ParsedDocument


def estimate_tokens(text: str) -> int:
    """Rough estimation of token count using word-ratio multiplier (~1.3 tokens per word)."""
    words = text.split()
    return max(1, int(len(words) * 1.3))


def chunk_parsed_document(
    parsed: ParsedDocument,
    source_uri: str,
    acl_scope: ACLScope | None = None,
    valid_to: datetime | None = None,
) -> list[Chunk]:
    """Structure-aware chunker converting document sections into typed Domain Chunks."""
    scope = acl_scope or ACLScope.public()
    temporal = TemporalBounds(
        valid_from=parsed.valid_from or datetime.now(UTC),
        valid_to=valid_to,
    )
    prov = Provenance.from_document(
        source_uri=source_uri,
        source_version=1,
    )

    chunks: list[Chunk] = []

    for idx, section in enumerate(parsed.sections):
        # Build clean chunk text containing heading context and section body
        section_heading = section.heading.strip()
        body = section.content.strip()

        # Generate deterministic chunk ID
        # Format: chk_{doc_id}_{idx}_{hash}
        chunk_id = generate_chunk_id(
            doc_id=parsed.doc_id,
            chunk_index=idx,
            text_content=body,
        )

        chunk = Chunk(
            chunk_id=chunk_id,
            doc_id=parsed.doc_id,
            index=idx,
            text=body,
            tokens=estimate_tokens(body),
            acl_scope=scope,
            temporal=temporal,
            provenance=prov,
            metadata={
                "heading": section_heading,
                "level": section.level,
                "section_index": idx,
                **parsed.metadata,
            },
        )
        chunks.append(chunk)

    return chunks
