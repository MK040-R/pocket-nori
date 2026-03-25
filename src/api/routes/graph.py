"""Graph routes — explainable Personal Context Graph surfaces."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.database import get_client
from src.knowledge_graph import find_path, get_neighbors, get_subgraph_for_conversation

router = APIRouter()

_NODE_TYPES = {"topic_node", "entity_node", "commitment"}


class GraphNode(BaseModel):
    type: str
    id: str
    label: str


class GraphEvidence(BaseModel):
    edge_id: str | None = None
    conversation_id: str
    segment_id: str | None = None
    snippet: str | None = None


class GraphNeighborEdge(BaseModel):
    edge_id: str
    source: GraphNode
    target: GraphNode
    relation_type: str
    confidence: float
    evidence_count: int
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    evidence: list[GraphEvidence]


class GraphSubgraphEdge(BaseModel):
    id: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    relation_type: str
    confidence: float
    evidence_count: int
    evidence: list[GraphEvidence]


class GraphNeighborsResponse(BaseModel):
    node_type: str
    node_id: str
    edges: list[GraphNeighborEdge]


class GraphSubgraphResponse(BaseModel):
    conversation_id: str
    nodes: list[GraphNode]
    edges: list[GraphSubgraphEdge]


class GraphPathResponse(BaseModel):
    from_id: str
    to_id: str
    nodes: list[GraphNode]
    edges: list[dict[str, Any]]


@router.get(
    "/neighbors/{node_type}/{node_id}",
    response_model=GraphNeighborsResponse,
    summary="Return the graph neighborhood for one node",
)
def neighbors(
    node_type: Literal["topic_node", "entity_node", "commitment"],
    node_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> GraphNeighborsResponse:
    if node_type not in _NODE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid node type",
        )
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)
    rows = get_neighbors(db, user_id, node_type, node_id)
    edges = [GraphNeighborEdge.model_validate(row) for row in rows]
    return GraphNeighborsResponse(node_type=node_type, node_id=node_id, edges=edges)


@router.get(
    "/subgraph",
    response_model=GraphSubgraphResponse,
    summary="Return the graph subgraph supported by one conversation",
)
def subgraph(
    conversation_id: str = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> GraphSubgraphResponse:
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)
    payload = get_subgraph_for_conversation(db, user_id, conversation_id)
    return GraphSubgraphResponse(
        conversation_id=conversation_id,
        nodes=[GraphNode.model_validate(row) for row in payload["nodes"]],
        edges=[GraphSubgraphEdge.model_validate(row) for row in payload["edges"]],
    )


@router.get(
    "/path",
    response_model=GraphPathResponse,
    summary="Find a path between two graph nodes",
)
def path(
    from_id: str = Query(...),
    to_id: str = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> GraphPathResponse:
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)
    payload = find_path(db, user_id, from_id, to_id)
    return GraphPathResponse(
        from_id=from_id,
        to_id=to_id,
        nodes=[GraphNode.model_validate(row) for row in payload["nodes"]],
        edges=payload["edges"],
    )
