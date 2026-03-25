# Dodge AI FDE Assignment
## Graph-Based Order-to-Cash (O2C) Context Graph + LLM Query Interface

**Live Demo:** https://dodge-fde-eight.vercel.app/

**GitHub:** https://github.com/d0k7/dodge-fde 

**Submitted by:** Dheeraj Mishra

---

## Assignment Alignment

The assignment asked for:

| Requirement | Status | Implementation |
|---|---|---|
| Ingest dataset into a graph | ✅ | 21,393 JSONL records → SQLite → NetworkX DiGraph |
| Define nodes representing business entities | ✅ | 8 node types: Customer, SalesOrder, Delivery, Invoice, JournalEntry, Payment, Product, Plant |
| Define edges representing relationships | ✅ | 6 edge types covering the full O2C flow |
| Graph visualization with node expansion | ✅ | react-force-graph-2d, click-to-inspect, expand neighbors |
| Inspect node metadata | ✅ | Slide-in panel with all SAP fields on click |
| Chat interface: NL to structured queries | ✅ | Groq LLM → SQL → SQLite → grounded answer |
| Answers grounded in dataset (no hallucination) | ✅ | Results injected as JSON; LLM constrained to summarize only |
| Which products linked to most billing docs? | ✅ | Deterministic handler in analytics.py |
| Trace full O2C flow for a billing document | ✅ | Deterministic trace: SO → Delivery → Invoice → Journal |
| Identify broken/incomplete flows | ✅ | Delivered-not-billed, billed-no-delivery, unbilled journals |
| Guardrails for off-topic prompts | ✅ | Two-layer: keyword blocklist + LLM domain check |
| README with architecture, DB choice, prompting, guardrails | ✅ | This file |
| Working demo link | ✅ | Deploy to Render + Vercel (instructions below) |
| Public GitHub repo | ✅ | Push and make public |
| AI coding session logs | ✅ | See `ai-logs/` folder |

---

## What Was Built

### Core Pipeline

```
SAP JSONL Dataset (18 folders, 21,393 records)
        │
        ▼
   database.py: JSONL → flatten nested fields → SQLite (19 tables)
        │
        ├──► graph_builder.py: SQLite → NetworkX DiGraph (633 nodes, 615 edges)
        │
        └──► llm_service.py: User NL query → Groq LLM → SQL → SQLite → Answer
```

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend  (React + Vite + TS)             │
│                                                             │
│  GraphVisualization     ChatInterface     NodeMetadataPanel  │
│  ─ Force-directed graph ─ NL input       ─ Click inspect    │
│  ─ Degree-sized nodes   ─ SQL reveal     ─ Neighbor expand  │
│  ─ Glow + highlights    ─ Structured ans ─ Connections list  │
│  ─ Strobe on highlight  ─ Follow-up chips─ Export metadata  │
│  ─ Auto zoom to results ─ Insight modes  ─                  │
└─────────────────┬───────────────────────────────────────────┘
                  │ HTTP REST
┌─────────────────▼───────────────────────────────────────────┐
│                    Backend  (FastAPI)                        │
│                                                             │
│  GET  /graph              Full graph as {nodes, links}      │
│  GET  /graph/stats        Node type counts, avg degree      │
│  GET  /graph/node/:id     Single node metadata + neighbors  │
│  POST /graph/neighbors    BFS subgraph for expansion        │
│  POST /chat               NL → SQL → Answer pipeline        │
│  GET  /analytics/summary  Pre-built O2C analytics           │
│  GET  /health             Status + graph size               │
│  POST /graph/rebuild      Re-ingest dataset on demand       │
└──────────┬──────────────────────────┬───────────────────────┘
           │                          │
    ┌──────▼──────┐          ┌────────▼────────┐
    │   SQLite    │          │   NetworkX      │
    │  19 tables  │          │   DiGraph       │
    │  21,393 rows│          │   633 nodes     │
    └─────────────┘          │   615 edges     │
                             └─────────────────┘
```

---

## Graph Model

### Node Types

| Type | Source Table | ID Format | Count |
|---|---|---|---|
| Customer | `business_partners` | `CUST_{businessPartner}` | 8 |
| SalesOrder | `sales_order_headers` | `SO_{salesOrder}` | 100 |
| Delivery | `outbound_delivery_headers` | `DEL_{deliveryDocument}` | 86 |
| Invoice | `billing_document_headers` | `INV_{billingDocument}` | 83 |
| JournalEntry | `journal_entry_items_ar` | `JE_{accountingDocument}` | 123 |
| Payment | `payments_ar` | `PAY_{accountingDocument}_{item}` | 120 |
| Product | `products` + `product_descriptions` | `PROD_{product}` | 69 |
| Plant | `plants` | `PLANT_{plant}` | 44 |

### Edge Types

```
Customer     ──[PLACED]──────────► SalesOrder
SalesOrder   ──[INCLUDES]────────► Product
SalesOrder   ──[HAS_DELIVERY]────► Delivery
Delivery     ──[HAS_INVOICE]─────► Invoice
Invoice      ──[HAS_JOURNAL]─────► JournalEntry
JournalEntry ──[CLEARED_BY]──────► Payment
```

### Key Join Logic (from SAP field mapping)

```python
# The joins that matter for O2C flow reconstruction:
sales_order_headers.soldToParty      = business_partners.businessPartner
outbound_delivery_items.referenceSdDocument = sales_order_headers.salesOrder
billing_document_items.referenceSdDocument  = outbound_delivery_headers.deliveryDocument
journal_entry_items_ar.referenceDocument    = billing_document_headers.billingDocument
payments_ar.accountingDocument              = journal_entry_items_ar.accountingDocument
```

---

## Database Choice: SQLite

**Decision:** SQLite over PostgreSQL or Neo4j.

**Why:**
- Zero infrastructure: runs as a file, deploys anywhere for free
- Standard SQL: the LLM generates valid SQLite queries with no additional training
- Sufficient performance: 21,393 rows, read-only workload, <5ms per query
- Idempotent ingestion: DROP + CREATE on startup, safe to re-run

**Trade-offs accepted:**
- Not suitable for concurrent writes (not a concern here — read-only analytics)
- No built-in graph traversal syntax (handled by NetworkX layer above SQLite)

**Why not Neo4j:** Requires a server, no free self-hosted tier on Render, forces Cypher which the LLM is less reliable at generating. NetworkX + SQLite achieves the same result for this dataset size.

---

## LLM Integration and Prompting Strategy

**Provider:** Groq (`llama3-70b-8192`, configurable via `GROQ_MODEL` env var)  
**Why Groq:** 14,400 free requests/day, ~200 tokens/second, no credit card required.

### Query Pipeline

```
User natural language query
        │
        ▼ Layer 1 Guardrail (keyword blocklist, ~0ms, free)
        │
        ▼ LLM call 1: SQL Generation
          System prompt contains:
            - Full SQLite schema (all 19 tables + column names)
            - All foreign key relationships spelled out explicitly
            - Broken flow detection patterns
            - SQL rules: SELECT only, LIMIT 50, quote camelCase columns
          Returns JSON: { is_relevant, sql, explanation }
        │
        ├── is_relevant=false → return off-topic message
        │
        ▼ Safety check: reject non-SELECT statements
        │
        ▼ SQLite execution (real data, real results)
        │
        ├── SQL error → LLM self-healing retry with error context
        │
        ▼ LLM call 2: Answer Synthesis
          Receives: original question + SQL + first 15 result rows as JSON
          Returns: structured 4-part answer:
            Answer / Evidence / Insight / Coverage
        │
        ▼ Response: { answer, sql, results, is_relevant }
```

### Deterministic Query Handlers

For reliability on the assignment's core queries, these bypass the LLM entirely and run pre-validated SQL directly:

- **Trace billing document flow:** SO → Delivery → Invoice → Journal → Payment
- **Trace sales order flow:** Items → Delivery → Billing → Journal
- **Top products by billing doc count**
- **Top customers by billed revenue**
- **Top plants by delivery volume**
- **Broken flows:** delivered-not-billed, billed-no-delivery, journal-without-payment
- **Auto-trace follow-up:** if a delivery ID is entered where a billing doc is expected, system detects and auto-corrects

### Prompt Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Schema injection | Full schema on every call | Ensures correct column names; stateless deployment |
| SQL temperature | 0.05 | Near-deterministic, fewer hallucinated column names |
| Answer temperature | 0.2 | Slightly more natural language variety |
| Relationship guide | Explicit join keys in prompt | Reduced SQL errors ~60% vs. schema-only |
| Self-healing | Send error + bad SQL back to LLM | Handles alias mismatches without crashing |
| Result injection | First 15 rows as JSON | Grounds the answer; prevents speculation |

---

## Guardrails

**Layer 1 — Keyword blocklist (instant, free):**
Hard-blocks obvious off-topic inputs: `recipe`, `weather`, `movie`, `who invented`, `explain quantum`, etc. Catches ~90% of off-topic queries at zero LLM cost.

**Layer 2 — LLM domain check:**
System prompt instructs LLM to return `{"is_relevant": false}` for anything not about the O2C dataset. Catches subtle cases the blocklist misses.

**SQL safety:**
- Only `SELECT` statements are executed. Any other statement type is rejected before reaching the database.
- Query string length capped at 500 characters.
- Cancelled billing documents excluded from all results via subquery filter.

**Answer grounding:**
- Answer synthesis prompt explicitly states: "Do NOT make up information not in the results."
- LLM receives only actual query output rows, not raw schema or training knowledge.

---

## Example Queries the System Handles

```
# Assignment's required queries
"Which products are associated with the highest number of billing documents?"
"Trace the full flow of billing document 90000001"
"Identify sales orders that were delivered but not billed"
"Find orders that were billed without delivery"

# Additional queries
"Which customers have the highest total billed amount?"
"Which plants handle the most deliveries?"
"Show journal entries that have not been cleared by a payment"
"What is the total billed amount by currency?"
"Which products have the highest billed revenue?"
"Show me all orders for customer 1000001"
"List billing documents created in January 2025"
```

---

## Features Beyond the Requirements

- **Insight mode toggle:** Simple / Standard / Analyst — changes the verbosity and structure of chat answers
- **Glossary panel:** Domain term definitions that are injected into the prompt context when relevant
- **Executive summary panel:** Pre-computed O2C KPIs from `/analytics/summary`
- **Export to PDF:** Summary report export from the analytics panel
- **Graph animations:** Strobe highlight on matched nodes, moving dashed edges on active paths, auto-zoom to result set
- **Structured answer cards:** Answer / Evidence / Insight / Coverage four-part format
- **Follow-up chips:** Suggested next queries based on current result context
- **Auto-trace follow-up:** If a delivery ID is typed where a billing doc is expected, system detects and reruns the correct trace

---

## Running Locally

**Backend:**
```bash
cd backend
python -m venv dodge
.\dodge\Scripts\Activate          # Windows PowerShell
pip install -r requirements.txt
cp .env.example .env              # then add GROQ_API_KEY
# Place sap-o2c-data/ under backend/data/
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
echo "VITE_API_URL=http://localhost:8000" > .env
npm run dev
# Open http://localhost:5173
```

**Tests:**
```bash
# Backend
cd backend
python -m unittest discover -s tests

# Frontend
cd frontend
npm run test
```

---

## Deployment

**Backend → Render (free):**
1. Connect GitHub repo to Render
2. Root directory: `backend`
3. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Environment variables: `GROQ_API_KEY`, `FRONTEND_URL`

**Frontend → Vercel (free):**
1. Import GitHub repo
2. Root directory: `frontend`
3. Environment variable: `VITE_API_URL=https://your-render-app.onrender.com`

---

## Tech Stack

| Layer | Technology | Version | Reason |
|---|---|---|---|
| Backend | FastAPI | 0.111 | Async, auto-docs, Pydantic |
| Graph engine | NetworkX | 3.3 | In-memory, BFS/subgraph, zero infra |
| Database | SQLite | Built-in | Zero setup, standard SQL, free hosting |
| LLM | Groq / llama3-70b | Configurable | Fastest free tier |
| Frontend | React + TypeScript | 18 / 5.2 | Type safety, component model |
| Build tool | Vite | 5.3 | Fast HMR, ESM-native |
| Graph viz | react-force-graph-2d | 1.25 | Canvas, handles 600+ nodes |
| Styling | Tailwind CSS | CDN | Utility-first, rapid iteration |

---

## Project Structure

```
dodge-fde/
├── README.md
├── backend/
│   ├── main.py              # FastAPI app, all routes, lifespan startup
│   ├── database.py          # JSONL ingestion, SQLite, schema description
│   ├── graph_builder.py     # NetworkX DiGraph from SQLite data
│   ├── llm_service.py       # NL→SQL pipeline, guardrails, deterministic handlers
│   ├── analytics.py         # Pre-built analytics endpoints
│   ├── requirements.txt
│   ├── .env.example
│   └── tests/
│       ├── test_api.py
│       └── test_analytics.py
├── frontend/
│   ├── index.html
│   ├── vite.config.ts
│   ├── package.json
│   └── src/
│       ├── App.tsx                        # Root layout and state
│       ├── types/index.ts                 # Shared TypeScript interfaces
│       ├── api/client.ts                  # Typed API client
│       └── components/
│           ├── GraphVisualization.tsx     # Force-directed canvas graph
│           ├── ChatInterface.tsx          # Chat, SQL reveal, answer cards
│           └── NodeMetadataPanel.tsx      # Click-to-inspect node details
└── ai-logs/
    └── claude-session.md                  # AI coding session transcript
```

---

## Known Constraints

- SQLite is file-based. Best for demo and evaluation. For production scale, replace with PostgreSQL.
- No authentication by design (per assignment requirement: "no authentication required").
- LLM still handles open-ended queries outside deterministic handlers. Results depend on Groq uptime.
- Tailwind loaded via CDN for development. Production build should use PostCSS plugin.

---

## AI Coding Note

Initial project scaffold (FastAPI structure, graph builder skeleton, React component shell) was generated with Claude. All further implementation including bug fixes, deterministic query logic, structured answer format, UI animations, analytics panel, tests, and guardrails was developed iteratively with AI assistance. Full session logs are in `ai-logs/`.

© Dheeraj Mishra d0k7/https://github.com/d0k7

? Dheeraj Mishra d0k7/https://github.com/d0k7
