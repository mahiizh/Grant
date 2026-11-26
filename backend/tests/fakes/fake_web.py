"""In-memory graspreach and web write-back fakes used by the test suite."""

from typing import Any

from app.web_grounding.web import WebPage, WebSearchError
from app.core.acl import ACLScope
from app.domain import Evidence, Provenance


class FakeWebClient:
    """Deterministic replacement for the external graspreach client."""

    def __init__(
        self,
        pages: list[WebPage] | None = None,
        error: str | None = None,
    ) -> None:
        self.pages = list(pages or [])
        self.error = error
        self.search_calls: list[str] = []
        self.read_calls: list[str] = []
        self.gather_calls: list[str] = []

    async def search(self, query: str) -> list[Any]:
        self.search_calls.append(query)
        if self.error:
            raise WebSearchError(self.error)
        return [page for page in self.pages if page.url]

    async def read(self, url: str) -> WebPage:
        self.read_calls.append(url)
        if self.error:
            raise WebSearchError(self.error)
        for page in self.pages:
            if page.url == url:
                return page
        raise WebSearchError(f"no fake page for {url}")

    async def gather(self, query: str) -> list[WebPage]:
        self.gather_calls.append(query)
        if self.error:
            raise WebSearchError(self.error)
        return [page for page in self.pages if page.text.strip()]


class FakeWebIngestor:
    """Records web write-back calls without touching Postgres/Qdrant/Neo4j."""

    def __init__(self, evidence: list[Evidence] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._evidence = evidence

    async def ingest(
        self,
        pages: list[WebPage],
        owner_user_id: str | None,
        acl_scope: ACLScope | None = None,
    ) -> list[Evidence]:
        self.calls.append(
            {
                "pages": list(pages),
                "owner_user_id": owner_user_id,
                "acl_scope": acl_scope,
            }
        )
        if self._evidence is not None:
            return self._evidence
        return [
            Evidence(
                chunk_id=f"web_{index}_{page.url}",
                doc_id=f"web:{page.url}",
                text=page.text,
                score=1.0,
                retrieval_method="web",
                provenance=Provenance.from_agent(page.url),
            )
            for index, page in enumerate(pages)
        ]
