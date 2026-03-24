"""
FastAPI Backend for Dodge AI FDE Assignment
Graph-Based Data Modeling and Query System

WHY FASTAPI:
  - Async-native: handles concurrent graph + chat requests without blocking
  - Auto-generates OpenAPI docs at /docs (useful for demo)
  - Pydantic validation out of the box
  - Deployable to Render free tier with uvicorn
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from database import ingest_dataset, get_schema_description
from graph_builder import build_graph, graph_to_json, get_neighbors, get_graph
from llm_service import chat
from analytics import get_summary

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ingest dataset and build graph."""
    logger.info("Starting up: ingesting dataset...")
    ingest_dataset()
    logger.info("Building graph...")
    build_graph()
    logger.info("Ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Dodge AI - O2C Graph System",
    description="Graph-based data modeling and LLM-powered query interface for Order-to-Cash data",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: allow frontend dev server and production domain
# Build explicit origins list - never use * with allow_credentials
_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
]
_frontend_url = os.getenv("FRONTEND_URL", "")
if _frontend_url:
    _origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


# ─── Request/Response Models ───────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    conversation_history: list[dict] | None = None


class ChatResponse(BaseModel):
    answer: str
    sql: str | None = None
    results: list[dict] = []
    is_relevant: bool = True
    error: str | None = None
    auto_followup: str | None = None
    auto_followup_reason: str | None = None


class NodeNeighborsRequest(BaseModel):
    node_id: str
    depth: int = 1


# ─── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check for deployment platforms."""
    G = get_graph()
    return {
        "status": "ok",
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
    }


@app.get("/graph")
async def get_full_graph():
    """
    Return the complete graph as {nodes, links} for frontend rendering.
    Called once on page load; frontend caches this.
    """
    G = get_graph()
    return graph_to_json(G)


@app.post("/graph/neighbors")
async def get_node_neighbors(req: NodeNeighborsRequest):
    """
    Return subgraph centered on a specific node.
    Used for 'expand node' interaction in the UI.
    """
    data = get_neighbors(req.node_id, req.depth)
    if not data["nodes"]:
        raise HTTPException(status_code=404, detail=f"Node '{req.node_id}' not found in graph")
    return data


@app.get("/graph/node/{node_id}")
async def get_node_metadata(node_id: str):
    """Return full metadata for a single node."""
    G = get_graph()
    if node_id not in G:
        raise HTTPException(status_code=404, detail="Node not found")
    attrs = dict(G.nodes[node_id])
    return {
        "id": node_id,
        "type": attrs.get("type"),
        "label": attrs.get("label"),
        "metadata": {k: v for k, v in attrs.items() if k not in ("type", "label")},
        "connections": G.degree(node_id),
        "predecessors": list(G.predecessors(node_id)),
        "successors": list(G.successors(node_id)),
    }


@app.get("/graph/stats")
async def get_graph_stats():
    """Graph statistics for the dashboard header."""
    G = get_graph()
    from collections import Counter
    type_counts = Counter(attrs.get("type", "Unknown") for _, attrs in G.nodes(data=True))
    return {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "node_types": dict(type_counts),
        "avg_degree": (
            sum(d for _, d in G.degree()) / G.number_of_nodes()
            if G.number_of_nodes() > 0
            else 0
        ),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """
    Main conversational query endpoint.
    Accepts natural language, returns data-backed answer.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=422, detail="Query cannot be empty")

    if len(req.query) > 500:
        raise HTTPException(status_code=422, detail="Query too long (max 500 chars)")

    result = chat(req.query.strip(), req.conversation_history)
    return ChatResponse(**result)


@app.post("/graph/rebuild")
async def rebuild_graph():
    """Force rebuild the graph (e.g. after uploading new data)."""
    ingest_dataset()
    G = build_graph()
    return {
        "message": "Graph rebuilt successfully",
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
    }


@app.get("/schema")
async def get_schema():
    """Return the database schema (useful for debugging)."""
    return {"schema": get_schema_description()}


@app.get("/analytics/summary")
async def analytics_summary():
    """Return executive summary metrics for the UI panel."""
    return get_summary()
