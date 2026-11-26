import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncGraphDatabase

from app.api.schemas.graph import (
    GraphLink,
    GraphNeighborsResponse,
    GraphNode,
    GraphPathResponse,
    GraphResponse,
)
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.core.store_guard import assert_writable_stores

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])


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


@router.get("", response_model=GraphResponse)
async def get_graph(
    scope: str | None = Query(None),
    limit: int = Query(100),
    source_kind: str | None = Query(None, pattern="^(document|web|chat|query|answer)$"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GraphResponse:
    """Retrieve ACL-filtered knowledge graph nodes and relationships from Neo4j."""
    filter_criteria = current_user.to_retrieval_filter(scope)
    node_pred, params = filter_criteria.to_cypher_predicate("n")
    rel_pred, _ = filter_criteria.to_cypher_predicate("r")
    node_pred = _with_source_kind(node_pred, params, "n", source_kind)

    driver = _get_driver()
    nodes: list[GraphNode] = []
    links: list[GraphLink] = []

    try:
        async with driver.session(database=get_settings().NEO4J_DATABASE) as session:
            # Query entity nodes
            node_cypher = f"""
            MATCH (n:Entity)
            WHERE {node_pred}
            RETURN n.id AS id, n.name AS name, n.entity_type AS type,
                   coalesce(n.aliases, []) AS aliases,
                   n.ingested_at AS ingested_at,
                   n.source_kind AS source_kind,
                   coalesce(n.source_kinds, []) AS source_kinds,
                   count {{ (n)--() }} AS degree
            LIMIT $limit
            """
            res_nodes = await session.run(node_cypher, limit=limit, **params)
            node_rows = await res_nodes.data()

            node_ids = set()
            for r in node_rows:
                node_id = r.get("id")
                node_name = r.get("name")
                if not node_id or not node_name:
                    continue
                node_ids.add(node_id)
                nodes.append(
                    GraphNode(
                        id=node_id,
                        name=node_name,
                        type=r.get("type") or "CONCEPT",
                        aliases=[str(a) for a in (r.get("aliases") or []) if str(a).strip()],
                        ingested_at=r.get("ingested_at"),
                        degree=int(r.get("degree") or 0),
                        source_kind=r.get("source_kind"),
                        source_kinds=[
                            str(kind)
                            for kind in (r.get("source_kinds") or [])
                            if str(kind).strip()
                        ],
                    )
                )

            # Query relationships
            rel_cypher = f"""
            MATCH (a:Entity)-[r]->(b:Entity)
            WHERE a.id IN $node_ids AND b.id IN $node_ids AND {rel_pred}
            RETURN a.id AS source, b.id AS target, type(r) AS label,
                   r.ingested_at AS ingested_at
            LIMIT $limit
            """
            res_rels = await session.run(rel_cypher, node_ids=list(node_ids), limit=limit, **params)
            rel_rows = await res_rels.data()

            for r in rel_rows:
                links.append(
                    GraphLink(
                        source=r["source"],
                        target=r["target"],
                        label=r["label"],
                        ingested_at=r.get("ingested_at"),
                    )
                )

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
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GraphNeighborsResponse:
    """Expand an ACL-filtered subgraph neighborhood centered on node_id in Neo4j."""
    filter_criteria = current_user.to_retrieval_filter(scope)
    center_pred, params = filter_criteria.to_cypher_predicate("n")
    neighbor_pred, _ = filter_criteria.to_cypher_predicate("b")
    rel_pred, _ = filter_criteria.to_cypher_predicate("r")
    center_pred = _with_source_kind(center_pred, params, "n", source_kind)
    neighbor_pred = _with_source_kind(neighbor_pred, params, "b", source_kind)

    driver = _get_driver()
    nodes: list[GraphNode] = []
    links: list[GraphLink] = []

    try:
        async with driver.session(database=get_settings().NEO4J_DATABASE) as session:
            # Fetch center node
            center_cypher = f"""
            MATCH (n:Entity)
            WHERE (n.id = $id OR toLower(n.name) = toLower($id)) AND {center_pred}
            RETURN n.id AS id, n.name AS name, n.entity_type AS type,
                   coalesce(n.aliases, []) AS aliases,
                   n.ingested_at AS ingested_at,
                   n.source_kind AS source_kind,
                   coalesce(n.source_kinds, []) AS source_kinds,
                   count {{ (n)--() }} AS degree
            """
            center_res = await session.run(center_cypher, id=node_id, **params)
            center = await center_res.single()
            if not center:
                raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")

            c_id = center["id"]
            nodes.append(
                GraphNode(
                    id=c_id,
                    name=center["name"],
                    type=center["type"] or "CONCEPT",
                    aliases=[str(a) for a in (center.get("aliases") or []) if str(a).strip()],
                    ingested_at=center.get("ingested_at"),
                    degree=int(center.get("degree") or 0),
                    source_kind=center.get("source_kind"),
                    source_kinds=[
                        str(kind)
                        for kind in (center.get("source_kinds") or [])
                        if str(kind).strip()
                    ],
                )
            )

            # Fetch 1-hop neighbors
            neighbor_cypher = f"""
            MATCH (a:Entity)-[r]-(b:Entity)
            WHERE a.id = $id AND {neighbor_pred} AND {rel_pred}
            RETURN b.id AS id, b.name AS name, b.entity_type AS type,
                   coalesce(b.aliases, []) AS aliases,
                   b.ingested_at AS ingested_at,
                   b.source_kind AS source_kind,
                   coalesce(b.source_kinds, []) AS source_kinds,
                   count {{ (b)--() }} AS degree,
                   startNode(r).id AS source, endNode(r).id AS target, type(r) AS label
            LIMIT 30
            """
            neighbor_res = await session.run(neighbor_cypher, id=c_id, **params)
            rows = await neighbor_res.data()
            seen_nodes = {c_id}

            for row in rows:
                if row["id"] not in seen_nodes:
                    seen_nodes.add(row["id"])
                    nodes.append(
                        GraphNode(
                            id=row["id"],
                            name=row["name"],
                            type=row["type"] or "CONCEPT",
                            aliases=[str(a) for a in (row.get("aliases") or []) if str(a).strip()],
                            ingested_at=row.get("ingested_at"),
                            degree=int(row.get("degree") or 0),
                            source_kind=row.get("source_kind"),
                            source_kinds=[
                                str(kind)
                                for kind in (row.get("source_kinds") or [])
                                if str(kind).strip()
                            ],
                        )
                    )
                links.append(
                    GraphLink(
                        source=row["source"],
                        target=row["target"],
                        label=row["label"],
                    )
                )
    finally:
        await driver.close()

    return GraphNeighborsResponse(
        center_node_id=node_id,
        depth=depth,
        nodes=nodes,
        links=links,
    )


@router.get("/path", response_model=GraphPathResponse)
async def get_graph_path(
    from_node: str = Query(..., alias="from"),
    to_node: str = Query(..., alias="to"),
    scope: str | None = Query(None),
    source_kind: str | None = Query(None, pattern="^(document|web|chat|query|answer)$"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GraphPathResponse:
    """Compute the shortest ACL-permitted path between two nodes in Neo4j."""
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
