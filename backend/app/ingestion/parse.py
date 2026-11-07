import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.domain.ids import generate_doc_id


class ParsedSection(BaseModel):
    """Logical section of a document bounded by markdown headers."""

    heading: str
    level: int
    content: str
    section_index: int


class ParsedDocument(BaseModel):
    """Structured representation of a parsed markdown document with extracted metadata."""

    doc_id: str
    title: str
    raw_content: str
    sections: list[ParsedSection] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    valid_from: datetime = Field(default_factory=lambda: datetime.now(UTC))
    valid_to: datetime | None = None


def parse_markdown(content: str, source_path: str | Path | None = None) -> ParsedDocument:
    """Parse a markdown document extracting title, document ID, metadata fields, and sections."""
    lines = content.splitlines()
    title = "Untitled Document"
    doc_id = ""
    metadata: dict[str, Any] = {}
    valid_from: datetime = datetime.now(UTC)
    valid_to: datetime | None = None

    # 0. Check for YAML front matter (--- ... ---)
    frontmatter_lines: list[str] = []
    body_lines: list[str] = []
    if lines and lines[0].strip() == "---":
        in_frontmatter = True
        for line in lines[1:]:
            if in_frontmatter:
                if line.strip() == "---":
                    in_frontmatter = False
                else:
                    frontmatter_lines.append(line)
            else:
                body_lines.append(line)
    else:
        body_lines = lines

    for fm_line in frontmatter_lines:
        if ":" in fm_line:
            k, v = fm_line.split(":", 1)
            key_clean = k.strip().lower().replace(" ", "_")
            val_clean = v.strip().strip("\"'")
            metadata[key_clean] = val_clean
            if key_clean == "title":
                title = val_clean
            elif key_clean in ("doc_id", "id"):
                doc_id = val_clean
            elif key_clean in ("valid_from", "date"):
                try:
                    valid_from = datetime.fromisoformat(val_clean.replace("Z", "+00:00"))
                    if valid_from.tzinfo is None:
                        valid_from = valid_from.replace(tzinfo=UTC)
                except Exception:
                    pass
            elif key_clean in ("valid_to",):
                try:
                    valid_to = datetime.fromisoformat(val_clean.replace("Z", "+00:00"))
                    if valid_to.tzinfo is None:
                        valid_to = valid_to.replace(tzinfo=UTC)
                except Exception:
                    pass

    # 1. Extract Title (# Title) from body if not set in frontmatter
    if title == "Untitled Document":
        for line in body_lines:
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                title = stripped[2:].strip()
                break

    # 2. Extract Document ID if explicitly given (e.g., **Document ID**: `doc_xyz`)
    if not doc_id:
        doc_id_match = re.search(r"\*\*Document ID\*\*:\s*`?([a-zA-Z0-9_\-]+)`?", content)
        if doc_id_match:
            doc_id = doc_id_match.group(1).strip()
        elif source_path:
            path_obj = Path(source_path)
            doc_id = generate_doc_id(path_obj.stem, version=1)
        else:
            doc_id = generate_doc_id(title, version=1)

    # 3. Extract Metadata key-value pairs (e.g. **Date of Incident**: 2026-04-12)
    meta_matches = re.findall(r"\*\*([a-zA-Z0-9_\s]+)\*\*:\s*`?([^`\n\r]+)`?", content)
    for k, v in meta_matches:
        key_clean = k.strip().lower().replace(" ", "_")
        val_clean = v.strip()
        metadata[key_clean] = val_clean

        # Parse date if available
        if "date" in key_clean or "updated" in key_clean:
            date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", val_clean)
            if date_match:
                try:
                    parsed_dt = datetime.strptime(date_match.group(1), "%Y-%m-%d").replace(
                        tzinfo=UTC
                    )
                    valid_from = parsed_dt
                except ValueError:
                    pass

    # 4. Extract Sections based on Markdown Headings (## or ###)
    sections: list[ParsedSection] = []
    section_pattern = re.compile(r"^(#{2,3})\s+(.+)$")

    current_heading = "Header & Metadata"
    current_level = 1
    current_lines: list[str] = []
    section_idx = 0

    for line in body_lines:
        match = section_pattern.match(line.strip())
        if match:
            # Save accumulated section if it contains text
            section_text = "\n".join(current_lines).strip()
            if section_text:
                sections.append(
                    ParsedSection(
                        heading=current_heading,
                        level=current_level,
                        content=section_text,
                        section_index=section_idx,
                    )
                )
                section_idx += 1
            current_level = len(match.group(1))
            current_heading = match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    # Add the final trailing section
    final_text = "\n".join(current_lines).strip()
    if final_text:
        sections.append(
            ParsedSection(
                heading=current_heading,
                level=current_level,
                content=final_text,
                section_index=section_idx,
            )
        )

    return ParsedDocument(
        doc_id=doc_id,
        title=title,
        raw_content=content,
        sections=sections,
        metadata=metadata,
        valid_from=valid_from,
        valid_to=valid_to,
    )
