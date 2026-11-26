import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncGraphDatabase
from sqlalchemy import select

from app.api.schemas.graph import (
    GraphChunkItem,
    GraphEntityChunksResponse,
    GraphLink,
    GraphNeighborsResponse,
    GraphNode,
    GraphPathResponse,
    GraphQueryDetailResponse,
    GraphResponse,
)
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.core.store_guard import assert_writable_stores
from app.db.models import AnswerRecord, EntityMentionRecord, QueryRecord
from app.db.postgres import get_db_session
from app.indexing.qdrant_indexer import QdrantIndexer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])

# Step 7: only Document, Entity and Query nodes are visible. Chunk text lives
# in Qdrant, and Answer/Message nodes remain graph lineage rather than UI nodes.
VISIBLE_NODE_TEST = "(n:Document OR n:Entity OR n:Query)"
VISIBLE_NODE_ID = "coalesce(n.id, n.doc_id)"
VISIBLE_NODE_NAME = "coalesce(n.name, n.title, n.raw_query, n.id, n.doc_id)"
VISIBLE_NODE_KIND = (
    "CASE WHEN n:Document THEN 'document' WHEN n:Query THEN 'query' "
    "ELSE toLower(coalesce(n.entity_type, 'concept')) END"
)


def _get_driver():
    settings = get_settings()
    assert_writable_stores(settings)
    return AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )


def _with_source_kind(
    predicate: str,
    params: dict[str, Any],
    alias: str,
    source_kind: str | None,
) -> str:
    """Add a parameterized source-kind filter to a Cypher node predicate."""
    if not source_kind:
        return predicate
    params["source_kind"] = source_kind
    return predicate + (
        f" AND ($source_kind IN coalesce({alias}.source_kinds, "
        f"[coalesce({alias}.source_kind, 'document')]))"
    )


def _with_min_cooccurrence(
    predicate: str,
    params: dict[str, Any],
    min_cooccurrence: int,
) -> str:
    """Filter aggregated edges by their Postgres-derived mention/co-occurrence count."""
    params["min_cooccurrence"] = min_cooccurrence
    return predicate + (
        " AND ($min_cooccurrence = 0 OR coalesce(r.count, 1) >= $min_cooccurrence)"
    )


def _node_from_row(row: dict[str, Any]) -> GraphNode:
    node_id = str(row.get("id") or "")
    return GraphNode(
        id=node_id,
        name=str(row.get("name") or node_id),
        type=str(row.get("type") or "entity"),
        node_kind=str(row.get("node_kind") or "entity"),
        aliases=[str(a) for a in (row.get("aliases") or []) if str(a).strip()],
        ingested_at=row.get("ingested_at"),
        degree=int(row.get("degree") or 0),
        source_kind=row.get("source_kind"),
        source_kinds=[str(kind) for kind in (row.get("source_kinds") or []) if str(kind).strip()],
        description=str(row.get("description") or row.get("name") or node_id),
    )


def _link_from_row(row: dict[str, Any]) -> GraphLink:
    return GraphLink(
        source=str(row["source"]),
        target=str(row["target"]),
        label=str(row.get("label") or "RELATES_TO"),
        count=int(row["count"]) if row.get("count") is not None else None,
        ingested_at=row.get("ingested_at"),
    )


@router.get("", response_model=GraphResponse)
async def get_graph(
    scope: str | None = Query(None),
    limit: int = Query(100),
    source_kind: str | None = Query(None, pattern="^(document|web|chat|query|answer)$"),
    min_cooccurrence: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GraphResponse:
    """Retrieve the ACL-filtered Document/Entity/Query graph from Neo4j."""
    filter_criteria = current_user.to_retrieval_filter(scope)
    node_pred, params = filter_criteria.to_cypher_predicate("n")
    rel_pred, _ = filter_criteria.to_cypher_predicate("r")
    node_pred = _with_source_kind(node_pred, params, "n", source_kind)
    rel_pred = _with_min_cooccurrence(rel_pred, params, min_cooccurrence)

    driver = _get_driver()
    nodes: list[GraphNode] = []
    links: list[GraphLink] = []

    try:
        async with driver.session(database=get_settings().NEO4J_DATABASE) as session:
            node_cypher = f"""
            MATCH (n)
            WHERE {VISIBLE_NODE_TEST} AND {node_pred}
            RETURN {VISIBLE_NODE_ID} AS id,
                   {VISIBLE_NODE_NAME} AS name,
                   {VISIBLE_NODE_KIND} AS type,
                   CASE WHEN n:Document THEN 'document'
                        WHEN n:Query THEN 'query' ELSE 'entity' END AS node_kind,
                   coalesce(n.aliases, []) AS aliases,
                   n.ingested_at AS ingested_at,
                   n.source_kind AS source_kind,
                   coalesce(n.source_kinds, []) AS source_kinds,
                   count {{ (n)--() }} AS degree
            LIMIT $limit
            """
            node_rows = await (await session.run(node_cypher, limit=limit, **params)).data()

            node_ids: set[str] = set()
            for row in node_rows:
                node_id = str(row.get("id") or "")
                if not node_id:
                    continue
                node_ids.add(node_id)
                nodes.append(_node_from_row(row))

            rel_cypher = f"""
            MATCH (a)-[r]->(b)
            WHERE (a:Document OR a:Entity OR a:Query)
              AND (b:Document OR b:Entity OR b:Query)
              AND coalesce(a.id, a.doc_id) IN $node_ids
              AND coalesce(b.id, b.doc_id) IN $node_ids
              AND {rel_pred}
            RETURN coalesce(a.id, a.doc_id) AS source,
                   coalesce(b.id, b.doc_id) AS target,
                   type(r) AS label,
                   coalesce(r.count, 0) AS count,
                   r.ingested_at AS ingested_at
            LIMIT $limit
            """
            rel_rows = await (
                await session.run(rel_cypher, node_ids=list(node_ids), limit=limit, **params)
            ).data()
            links = [_link_from_row(row) for row in rel_rows]
    finally:
        await driver.close()

    return GraphResponse(
        nodes=nodes,
        links=links,
        total_nodes=len(nodes),
        total_links=len(links),
    )


@router.get("/nodes/{node_id}/neighbors", response_model=GraphNeighborsResponse)
async def get_node_neighbors(
    node_id: str,
    depth: int = Query(1),
    scope: str | None = Query(None),
    source_kind: str | None = Query(None, pattern="^(document|web|chat|query|answer)$"),
    min_cooccurrence: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GraphNeighborsResponse:
    """Expand the ACL-filtered one-hop neighborhood of any visible graph node."""
    filter_criteria = current_user.to_retrieval_filter(scope)
    center_pred, params = filter_criteria.to_cypher_predicate("n")
    neighbor_pred, _ = filter_criteria.to_cypher_predicate("b")
    rel_pred, _ = filter_criteria.to_cypher_predicate("r")
    center_pred = _with_source_kind(center_pred, params, "n", source_kind)
    neighbor_pred = _with_source_kind(neighbor_pred, params, "b", source_kind)
    rel_pred = _with_min_cooccurrence(rel_pred, params, min_cooccurrence)

    driver = _get_driver()
    nodes: list[GraphNode] = []
    links: list[GraphLink] = []

    try:
        async with driver.session(database=get_settings().NEO4J_DATABASE) as session:
            center_cypher = f"""
            MATCH (n)
            WHERE {VISIBLE_NODE_TEST}
              AND (n.id = $id OR n.doc_id = $id
                   OR toLower(coalesce(n.name, n.title, n.raw_query, '')) = toLower($id))
              AND {center_pred}
            RETURN {VISIBLE_NODE_ID} AS id,
                   {VISIBLE_NODE_NAME} AS name,
                   {VISIBLE_NODE_KIND} AS type,
                   CASE WHEN n:Document THEN 'document'
                        WHEN n:Query THEN 'query' ELSE 'entity' END AS node_kind,
                   coalesce(n.aliases, []) AS aliases,
                   n.ingested_at AS ingested_at,
                   n.source_kind AS source_kind,
                   coalesce(n.source_kinds, []) AS source_kinds,
                   count {{ (n)--() }} AS degree
            LIMIT 1
            """
            center = await (await session.run(center_cypher, id=node_id, **params)).single()
            if not center:
                raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")

            c_id = str(center["id"])
            nodes.append(_node_from_row(dict(center)))

            neighbor_cypher = f"""
            MATCH (a)-[r]-(b)
            WHERE (a.id = $id OR a.doc_id = $id)
              AND (b:Document OR b:Entity OR b:Query)
              AND {neighbor_pred} AND {rel_pred}
            RETURN {VISIBLE_NODE_ID.replace('n.', 'b.')} AS id,
                   coalesce(b.name, b.title, b.raw_query, b.id, b.doc_id) AS name,
                   CASE WHEN b:Document THEN 'document' WHEN b:Query THEN 'query'
                        ELSE toLower(coalesce(b.entity_type, 'concept')) END AS type,
                   CASE WHEN b:Document THEN 'document'
                        WHEN b:Query THEN 'query' ELSE 'entity' END AS node_kind,
                   coalesce(b.aliases, []) AS aliases,
                   b.ingested_at AS ingested_at,
                   b.source_kind AS source_kind,
                   coalesce(b.source_kinds, []) AS source_kinds,
                   count {{ (b)--() }} AS degree,
                   coalesce(startNode(r).id, startNode(r).doc_id) AS source,
                   coalesce(endNode(r).id, endNode(r).doc_id) AS target,
                   type(r) AS label,
                   coalesce(r.count, 0) AS count
            LIMIT 30
            """
            rows = await (
                await session.run(neighbor_cypher, id=c_id, limit=30, **params)
            ).data()
            seen_nodes = {c_id}

            for row in rows:
                row_id = str(row.get("id") or "")
                if row_id and row_id not in seen_nodes:
                    seen_nodes.add(row_id)
                    nodes.append(_node_from_row(row))
                links.append(_link_from_row(row))
    finally:
        await driver.close()

    return GraphNeighborsResponse(
        center_node_id=node_id,
        depth=depth,
        nodes=nodes,
        links=links,
    )


@router.get("/entities/{entity_id}/chunks", response_model=GraphEntityChunksResponse)
async def get_entity_chunks(
    entity_id: str,
    scope: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    session=Depends(get_db_session),
) -> GraphEntityChunksResponse:
    """Return chunk texts for an entity via Postgres mentions and Qdrant payloads.

    Every Qdrant payload is rechecked against the caller's ACL before its text
    is returned, so an entity shared across owners cannot leak another owner's
    chunk content through the graph UI.
    """
    filter_criteria = current_user.to_retrieval_filter(scope)
    rows = (
        (
            await session.execute(
                select(EntityMentionRecord)
                .where(EntityMentionRecord.entity_id == entity_id)
                .order_by(EntityMentionRecord.mention_count.desc(), EntityMentionRecord.id)
                .limit(limit * 4)
            )
        )
        .scalars()
        .all()
    )
    chunk_ids = list(dict.fromkeys(str(row.chunk_id) for row in rows if row.chunk_id))[:limit]

    qdrant = QdrantIndexer()
    try:
        payloads = await qdrant.get_chunks(chunk_ids)
    finally:
        await qdrant.close()

    chunks: list[GraphChunkItem] = []
    for row in rows:
        chunk_id = str(row.chunk_id or "")
        payload = payloads.get(chunk_id)
        if not payload or not filter_criteria.permits_payload(payload):
            continue
        chunks.append(
            GraphChunkItem(
                chunk_id=chunk_id,
                doc_id=str(payload.get("doc_id") or row.doc_id or "") or None,
                text=str(payload.get("text") or ""),
                source_kind=str(payload.get("source_kind") or row.source_kind or "") or None,
                title=payload.get("title"),
                url=payload.get("url"),
                mention_count=int(row.mention_count or 0),
            )
        )
        if len(chunks) >= limit:
            break

    return GraphEntityChunksResponse(entity_id=entity_id, chunks=chunks)


@router.get("/queries/{query_id}", response_model=GraphQueryDetailResponse)
async def get_query_detail(
    query_id: str,
    scope: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    session=Depends(get_db_session),
) -> GraphQueryDetailResponse:
    """Return a Query node's stored answer, source and path to the UI.

    Query/Answer rows carry an owner_user_id; only that owner (or an admin) may
    read them. ``scope`` is validated so a caller cannot widen the boundary by
    naming a shared scope they do not hold.
    """
    current_user.resolve_scope(scope)
    row = (
        await session.execute(
            select(QueryRecord, AnswerRecord)
            .join(AnswerRecord, AnswerRecord.query_id == QueryRecord.query_id)
            .where(QueryRecord.query_id == query_id)
            .order_by(AnswerRecord.created_at.desc())
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Query '{query_id}' not found.")

    query, answer = row
    owner = answer.owner_user_id or query.owner_user_id
    if not current_user.is_admin and owner != current_user.user_id:
        raise HTTPException(status_code=404, detail=f"Query '{query_id}' not found.")

    return GraphQueryDetailResponse(
        query_id=query.query_id,
        query=query.raw_query,
        rewritten_query=query.rewritten_query,
        answer=answer.content,
        source=answer.source,
        path=list(answer.path or []),
        top_score=float(answer.top_score or 0.0),
        answer_policy=query.answer_policy,
        created_at=query.created_at.isoformat() if query.created_at else None,
    )


@router.get("/path", response_model=GraphPathResponse)
async def get_graph_path(
    from_node: str = Query(..., alias="from"),
    to_node: str = Query(..., alias="to"),
    scope: str | None = Query(None),
    source_kind: str | None = Query(None, pattern="^(document|web|chat|query|answer)$"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GraphPathResponse:
    """Compute the shortest ACL-permitted path between two entities in Neo4j."""
    filter_criteria = current_user.to_retrieval_filter(scope)
    node_pred, params = filter_criteria.to_cypher_predicate("n")
    rel_pred, _ = filter_criteria.to_cypher_predicate("r")
    start_pred, _ = filter_criteria.to_cypher_predicate("a")
    target_pred, _ = filter_criteria.to_cypher_predicate("b")
    start_pred = _with_source_kind(start_pred, params, "a", source_kind)
    target_pred = _with_source_kind(target_pred, params, "b", source_kind)
    node_pred = _with_source_kind(node_pred, params, "n", source_kind)

    driver = _get_driver()
    try:
        async with driver.session(database=get_settings().NEO4J_DATABASE) as session:
            cypher = f"""
            MATCH (a:Entity), (b:Entity)
            WHERE (a.id = $from OR toLower(a.name) = toLower($from))
              AND (b.id = $to OR toLower(b.name) = toLower($to))
              AND {start_pred}
              AND {target_pred}
            MATCH path = (a)-[*..5]-(b)
            WHERE ALL(n IN nodes(path) WHERE 'Entity' IN labels(n) AND {node_pred})
              AND ALL(r IN relationships(path) WHERE {rel_pred})
            RETURN [n IN nodes(path) | n.name] AS node_names,
                   [r IN relationships(path) | {{source: startNode(r).id, target: endNode(r).id, label: type(r)}}] AS rels
            ORDER BY length(path)
            LIMIT 1
            """
            res = await session.run(cypher, **{"from": from_node, "to": to_node}, **params)
            record = await res.single()

            if not record:
                return GraphPathResponse(
                    from_node=from_node,
                    to_node=to_node,
                    found=False,
                    path=[],
                    hops=0,
                    links=[],
                )

            node_names = record["node_names"]
            rels = record["rels"]
            links = [
                GraphLink(
                    source=r["source"],
                    target=r["target"],
                    label=r["label"],
                )
                for r in rels
            ]

            return GraphPathResponse(
                from_node=from_node,
                to_node=to_node,
                found=True,
                path=node_names,
                hops=len(rels),
                links=links,
            )
    finally:
        await driver.close()
