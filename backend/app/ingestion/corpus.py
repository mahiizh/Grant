"""Canonical corpus discovery shared by ingestion, evaluation, and tests.

The corpus has three kinds of files: the hand-authored documents at the root,
adversarial benchmark documents under ``adversarial/``, and generated synthetic
documents under ``synthetic/``. Keeping the walk in one place prevents the live
ingest and the hermetic harness from silently scoring different corpora.
"""

from collections.abc import Iterator
from pathlib import Path

# Directories under ``corpus/`` that contain benchmark documents. Root-level
# ``*.md`` files are included separately.
SUBDIRECTORIES = ("adversarial", "synthetic")


def iter_corpus_files(corpus_dir: Path | str) -> Iterator[Path]:
    """Yield every markdown document that belongs in the ingested corpus.

    ``README.md`` files are documentation, not corpus content, and are skipped
    at every level. Files are sorted so ingestion order (and therefore any
    order-sensitive test) is deterministic.
    """
    root = Path(corpus_dir)
    if not root.exists():
        raise FileNotFoundError(f"Corpus directory not found at: {root}")

    files = [path for path in sorted(root.glob("*.md")) if path.name.lower() != "readme.md"]
    for name in SUBDIRECTORIES:
        directory = root / name
        if not directory.exists():
            continue
        files.extend(
            path for path in sorted(directory.glob("*.md")) if path.name.lower() != "readme.md"
        )
    return iter(files)
