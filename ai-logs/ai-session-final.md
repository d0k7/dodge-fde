# AI Session Logs - Claude plus Codex - Dodge AI FDE Assignment
Tool: Claude and Codex
Session dates: 22 March 2026 to 25 March 2026
Project: Dodge AI FDE Assignment, SAP O2C Graph System
Developer: Dheeraj Mishra, GitHub d0k7

## Claude AI Session Log
Tool: Claude, Anthropic, claude.ai

### Session Overview
Claude was used for initial system architecture, full backend implementation, frontend scaffold, and all major rewrites when the real dataset schema was confirmed. It also handled the final bug audit, CORS hardening, and README writing.

### Architecture and Technology Decisions
- Chose SQLite over PostgreSQL and Neo4j for zero infrastructure, standard SQL compatible with LLM generation, free on Render, and sufficient for 21,393 read only rows.
- Chose NetworkX in memory DiGraph over a graph database because no server is required and BFS subgraph expansion is built in.
- Chose Groq with Llama 3 70B for a fast free tier and stable SQL generation.
- Chose react force graph 2d because it is canvas based and matches the reference UI.

### Backend
- Designed and implemented FastAPI routes for graph, chat, node metadata, neighbor expansion, analytics summary, and health check.
- Implemented JSONL ingestion in database.py with folder detection across 18 entity subfolders, line by line parsing, recursive flattening of nested SAP time objects, camelCase column preservation, and idempotent DROP and CREATE on startup.
- Built NetworkX DiGraph in graph_builder.py using real SAP field names such as salesOrder, soldToParty, billingDocument, referenceSdDocument, referenceDocument, and accountingDocument, with cancellation exclusion.
- Implemented NL to SQL pipeline in llm_service.py with full schema injection, explicit join guide, SQL generation at temperature 0.05, structured JSON output, self healing retry on SQL errors, and answer synthesis at temperature 0.2.
- Implemented two layer guardrails with a keyword blocklist and an LLM domain classifier, plus SELECT only enforcement.
- Fixed data loss where valid 0 and False values were converted to empty strings by replacing or with explicit None checks.
- Fixed SQLite connection leak on SQL error path by closing the connection before retry.
- Fixed CORS configuration by removing wildcard origins combined with allow_credentials and switching to explicit origin list from environment variables.

### Frontend
- Scaffolded React plus TypeScript plus Vite with typed API client and shared interfaces.
- Built GraphVisualization.tsx with force directed canvas graph, degree based node sizing, per type ambient glow via radial gradients, highlighted path rendering, and fit to view on load and on result highlight.
- Added finite coordinate guards on all canvas draw callbacks to prevent crashes during force simulation initialization.
- Built ChatInterface.tsx with NL input, SQL reveal toggle, structured answer display, typing indicator, example query suggestions, and node highlight coordination.
- Built NodeMetadataPanel.tsx with click to inspect overlay, full SAP field metadata, and predecessor and successor lists.
- Applied dark premium UI with a #0A0B0F background, glass panels, indigo accents, subtle grid texture, and stats pills.
- Fixed TypeScript types by adding Product and Payment to the GraphNode union.
- Removed unused prop from GraphVisualization props to resolve TypeScript contract mismatch.

### Deployment Support
- Configured Vite proxy for local development.
- Documented Render deployment settings and environment variables.
- Documented Vercel deployment settings and VITE_API_URL.
- Added .env.example with required and optional variables.

### Documentation
- Wrote full README covering assignment alignment, architecture, graph model, database choice, LLM pipeline, guardrails, example queries, deployment instructions, and tech stack table.

### Notable Issues Resolved
- JSONL dataset schema mismatch resolved by full rewrite to folder based JSONL ingestion.
- Canvas non finite coordinate crash resolved by draw guards.
- Tailwind CSS missing resolved by adding CDN script in index.html.
- CORS wildcard with credentials resolved by explicit allow list.

### Session Stats
| Metric | Value |
| --- | --- |
| Major iterations | 8 |
| Files created | 16 |
| Full rewrites | 2, database.py and graph_builder.py |
| Bugs fixed | 8 |
| UI redesigns | 1 |

## Codex AI Session Log
Tool: Codex, OpenAI

### Session Overview
Codex focused on stabilizing the running system, improving UX, hardening the NL to SQL pipeline, adding deterministic analytics, and supporting deployment to Render and Vercel. It also resolved critical runtime errors in the hosted environment.

### Major Fixes and Features
Backend:
- Added deterministic handlers for core assignment queries including trace billing flow, top billed products, top customers, and broken flow checks.
- Added structured response fields and auto follow up logic in C:\Users\dheer\Downloads\dodge-fde\backend\llm_service.py.
- Added strict SQL safety checks and LLM retry flow for SQL errors.
- Updated default Groq model to a supported version and made it configurable by environment.
- Pinned httpx to resolve Groq client proxy errors on Render.
- Expanded CORS handling to allow preflight OPTIONS and multiple frontend origins.
- Enabled HEAD on health check endpoint to support uptime monitors.
- Added runtime pin for Render using python 3.11.9.

Frontend:
- Added Answer, Evidence, Insight, Coverage response cards.
- Added Explain simply and Key takeaways actions.
- Added copy report and show SQL actions.
- Added follow up suggestions with dedupe and a single Next best step UX.
- Added animated thinking indicator during LLM calls.
- Added highlight nodes behavior with red green strobe, moving dashed edges, and auto zoom to result set.
- Fixed graph crash from undefined coordinates and improved hover and selection styling.

Deployment:
- Deployed backend to Render and frontend to Vercel.
- Fixed CORS errors by aligning FRONTEND_URL and FRONTEND_URLS with Vercel domains.

Repository hygiene:
- Created C:\Users\dheer\Downloads\dodge-fde\README.md and updated it for final submission.
- Added C:\Users\dheer\Downloads\dodge-fde\.gitignore.
- Created AI logs folder and combined session log.

### Notable Errors Resolved
- Groq model decommission error fixed by switching default model.
- Render build failures fixed by pinning runtime.
- CORS preflight failures fixed by allowing OPTIONS and multiple frontend origins.
- Uptime monitor 405 fixed by enabling HEAD on health endpoint.

### Session Stats
| Metric | Value |
| --- | --- |
| Major iterations | 10 plus |
| Features added | 12 plus |
| Deployment issues resolved | 6 |

## Deliverable Files for Submission
- C:\Users\dheer\Downloads\dodge-fde\ai-logs\ai-session-final.md
- C:\Users\dheer\Downloads\dodge-fde\README.md
- C:\Users\dheer\Downloads\dodge-fde\.gitignore
