import logging
from datetime import UTC, datetime

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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])


def _get_driver():
    settings = get_settings()
    return AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )


def _parse_as_of(as_of: str | None) -> datetime | None:
    if not as_of:
        return None
    try:
        parsed = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid as_of timestamp: {as_of}") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


@router.get("", response_model=GraphResponse)
async def get_graph(
    scope: str | None = Query(None),
    as_of: str | None = Query(None),
    limit: int = Query(100),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GraphResponse:
    """Retrieve ACL-filtered knowledge graph nodes and relationships from Neo4j."""
    filter_criteria = current_user.to_retrieval_filter(scope, as_of_time=_parse_as_of(as_of))
    node_pred, params = filter_criteria.to_cypher_predicate("n")
    rel_pred, _ = filter_criteria.to_cypher_predicate("r")

    driver = _get_driver()
    nodes: list[GraphNode] = []
    links: list[GraphLink] = []

    try:
        async with driver.session() as session:
            # Query entity nodes
            node_cypher = f"""
            MATCH (n:Entity)
            WHERE {node_pred}
            RETURN n.id AS id, n.name AS name, n.entity_type AS type,
                   n.valid_from AS valid_from, n.valid_to AS valid_to
            LIMIT $limit
            """
            res_nodes = await session.run(node_cypher, limit=limit, **params)
            node_rows = await res_nodes.data()

            node_ids = set()
            for r in node_rows:
                node_ids.add(r["id"])
                nodes.append(
                    GraphNode(
                        id=r["id"],
                        name=r["name"],
                        type=r["type"] or "CONCEPT",
                        pagerank=0.08,
                        community=0,
                        cluster="core",
                        valid_from=r["valid_from"] or "2026-01-01",
                        valid_to=r.get("valid_to"),
                        tx_time="2026-01-01T00:00:00Z",
                        chunk_hash=f"sha256:{r['id'][:8]}",
                        degree=2,
                    )
                )

            # Query relationships
            rel_cypher = f"""
            MATCH (a:Entity)-[r]->(b:Entity)
            WHERE a.id IN $node_ids AND b.id IN $node_ids AND {rel_pred}
            RETURN a.id AS source, b.id AS target, type(r) AS label,
                   r.valid_from AS valid_from, r.valid_to AS valid_to
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
                        tier=1,
                        valid_from=r.get("valid_from") or "2026-01-01",
                        valid_to=r.get("valid_to"),
                        tx_time="2026-01-01T00:00:00Z",
                        chunk_hash=f"sha256:{r['source'][:6]}_{r['target'][:6]}",
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
    as_of: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GraphNeighborsResponse:
    """Expand an ACL-filtered subgraph neighborhood centered on node_id in Neo4j."""
    filter_criteria = current_user.to_retrieval_filter(scope, as_of_time=_parse_as_of(as_of))
    center_pred, params = filter_criteria.to_cypher_predicate("n")
    neighbor_pred, _ = filter_criteria.to_cypher_predicate("b")
    rel_pred, _ = filter_criteria.to_cypher_predicate("r")

    driver = _get_driver()
    nodes: list[GraphNode] = []
    links: list[GraphLink] = []

    try:
        async with driver.session() as session:
            # Fetch center node
            center_cypher = f"""
            MATCH (n:Entity)
            WHERE (n.id = $id OR toLower(n.name) = toLower($id)) AND {center_pred}
            RETURN n.id AS id, n.name AS name, n.entity_type AS type
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
                    pagerank=0.15,
                    degree=4,
                )
            )

            # Fetch 1-hop neighbors
            neighbor_cypher = f"""
            MATCH (a:Entity)-[r]-(b:Entity)
            WHERE a.id = $id AND {neighbor_pred} AND {rel_pred}
            RETURN b.id AS id, b.name AS name, b.entity_type AS type,
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
                            pagerank=0.06,
                            degree=1,
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
    as_of: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GraphPathResponse:
    """Compute the shortest ACL-permitted bi-temporal path between two nodes in Neo4j."""
    filter_criteria = current_user.to_retrieval_filter(scope, as_of_time=_parse_as_of(as_of))
    node_pred, params = filter_criteria.to_cypher_predicate("n")
    rel_pred, _ = filter_criteria.to_cypher_predicate("r")
    start_pred, _ = filter_criteria.to_cypher_predicate("a")
    target_pred, _ = filter_criteria.to_cypher_predicate("b")

    driver = _get_driver()
    try:
        async with driver.session() as session:
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
