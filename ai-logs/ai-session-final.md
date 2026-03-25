# AI Session Logs - Claude plus Codex - Dodge AI FDE Assignment
Tool: Claude and Codex
Session dates: 22 March 2026 to 25 March 2026
Project: Dodge AI Forward Deployed Engineer Take Home Assignment
Developer: Dheeraj Mishra, GitHub d0k7

## Claude AI Session Log

### Session Overview
This log covers the full Claude coding session for the Dodge AI FDE assignment. The session spanned multiple conversations and covered architecture design, full backend implementation, frontend implementation, bug fixing, and final README writing.

### Prompt 1 - Project Kickoff
User prompt paraphrased:
Shared the full assignment document for a graph based O2C system with an LLM query interface, the role description for the FDE role at Dodge AI, and a project initiation prompt with FAANG plus quality standards. Asked to start building the assignment.

Claude reasoning:
- Identified the core deliverable as JSONL dataset to SQLite to NetworkX graph to React visualization plus LLM chat.
- Chose SQLite over PostgreSQL for zero infra, standard SQL for LLM generation, and free Render deployment.
- Chose NetworkX over Neo4j because in memory traversal is sufficient for 600 plus nodes and needs no server.
- Chose Groq over OpenAI for free tier and fast inference with Llama 3 70B for SQL generation.
- Chose react force graph 2d to match the reference UI screenshots.

Files generated:
- C:\Users\dheer\Downloads\dodge-fde\backend\database.py
- C:\Users\dheer\Downloads\dodge-fde\backend\graph_builder.py
- C:\Users\dheer\Downloads\dodge-fde\backend\llm_service.py
- C:\Users\dheer\Downloads\dodge-fde\backend\main.py
- C:\Users\dheer\Downloads\dodge-fde\backend\requirements.txt
- C:\Users\dheer\Downloads\dodge-fde\backend\.env.example
- C:\Users\dheer\Downloads\dodge-fde\frontend\package.json
- C:\Users\dheer\Downloads\dodge-fde\frontend\vite.config.ts
- C:\Users\dheer\Downloads\dodge-fde\frontend\src\types\index.ts
- C:\Users\dheer\Downloads\dodge-fde\frontend\src\api\client.ts
- C:\Users\dheer\Downloads\dodge-fde\frontend\src\components\GraphVisualization.tsx
- C:\Users\dheer\Downloads\dodge-fde\frontend\src\components\ChatInterface.tsx
- C:\Users\dheer\Downloads\dodge-fde\frontend\src\components\NodeMetadataPanel.tsx
- C:\Users\dheer\Downloads\dodge-fde\frontend\src\App.tsx
- C:\Users\dheer\Downloads\dodge-fde\frontend\src\main.tsx
- C:\Users\dheer\Downloads\dodge-fde\frontend\index.html

Key architectural decisions:
- SQLite for zero infra, LLM friendly SQL, free deployment, and fast queries for 21k rows.
- NetworkX for in memory traversal and BFS subgraphs without a graph server.
- Groq for free tier and speed, using Llama 3 70B for SQL generation.
- react force graph 2d for visual parity with the reference screenshots.

### Prompt 2 - Dataset Format Discovery plus Full Rewrite
User prompt paraphrased:
Shared the actual dataset schema. The dataset is JSONL in 18 subfolders under sap o2c data. Camel case field names and nested objects need flattening. The backend is running.

Bug identified:
Original database ingestion assumed CSV or Excel. Actual dataset is JSONL folders with camel case fields.

Claude reasoning:
- Full rewrite of database ingestion for folder based JSONL parsing and recursive flattening.
- Graph builder rewritten for real SAP field names and joins.
- LLM prompt updated with explicit foreign key relationships.

Files rewritten:
- C:\Users\dheer\Downloads\dodge-fde\backend\database.py
- C:\Users\dheer\Downloads\dodge-fde\backend\graph_builder.py
- C:\Users\dheer\Downloads\dodge-fde\backend\llm_service.py

Result after fix:
Loaded 19 tables and built a graph with 633 nodes and 615 edges.

### Prompt 3 - Frontend Files Not Showing
User prompt:
Vite template showing on localhost and no custom UI files present.

Root cause:
Custom frontend files were not created in the Vite project.

Claude action:
Generated all frontend files with correct destination paths.

### Prompt 4 - UI Rendering Issue
User prompt:
Unstyled page and graph disappearing after load.

Bugs:
- Tailwind not installed.
- Force graph drawing code used non finite node positions before layout stabilizes.

Fixes:
- Added Tailwind CDN script to C:\Users\dheer\Downloads\dodge-fde\frontend\index.html.
- Added finite guards before canvas drawing.

### Prompt 5 - Premium UI Redesign
User prompt:
Asked for FAANG plus quality UI.

Claude design updates:
- Dark theme with glass panels.
- Degree based node sizing and glow effects.
- Custom link rendering for highlighted paths.
- Enhanced chat UI with typing dots.
- Grid overlay and stats pills.
- Improved node metadata panel formatting.

Files updated:
- C:\Users\dheer\Downloads\dodge-fde\frontend\src\App.tsx
- C:\Users\dheer\Downloads\dodge-fde\frontend\src\components\GraphVisualization.tsx
- C:\Users\dheer\Downloads\dodge-fde\frontend\src\components\ChatInterface.tsx
- C:\Users\dheer\Downloads\dodge-fde\frontend\src\components\NodeMetadataPanel.tsx

### Prompt 6 - Canvas Non Finite Error After Redesign
User prompt:
createRadialGradient error due to non finite values.

Fix:
Reapplied finite guards for node and link drawing in C:\Users\dheer\Downloads\dodge-fde\frontend\src\components\GraphVisualization.tsx.

### Prompt 7 - Codex Audit Fixes
User prompt:
Shared a Codex audit report and asked Claude to fix issues and write README.

Fixes applied:
- Preserve zero and false values in JSONL ingest in C:\Users\dheer\Downloads\dodge-fde\backend\database.py.
- Close SQLite connection on SQL error in C:\Users\dheer\Downloads\dodge-fde\backend\llm_service.py.
- Add Product, Plant, Payment types in C:\Users\dheer\Downloads\dodge-fde\frontend\src\types\index.ts.
- Remove unused prop on GraphVisualization.
- Fix CORS wildcard with credentials in C:\Users\dheer\Downloads\dodge-fde\backend\main.py.
- Clean up LLM prompt alias assumption.
- Fix encoding artifacts and hard coded counts in UI.

### Prompt 8 - Final README
User prompt:
Asked for a README aligned to assignment requirements.

Claude output:
A full README with alignment table, architecture diagram, graph model table, LLM pipeline, guardrails, example queries, deployment instructions, and tech stack.

## Codex AI Session Log

### Session Overview
Codex focused on stabilizing the running system, improving UX, hardening the NL to SQL pipeline, adding deterministic analytics, and supporting deployment to Render and Vercel. It also resolved critical runtime errors in the hosted environment.

### Major Fixes and Features
Backend:
- Added deterministic handlers for core assignment queries including trace billing flow, top billed products, top customers, and broken flow checks.
- Added structured response fields and auto follow up logic in C:\Users\dheer\Downloads\dodge-fde\backend\llm_service.py.
- Added strict SQL safety checks and LLM retry flow for SQL errors.
- Updated default Groq model to a supported version and made it configurable by environment.
- Pinned httpx to resolve Groq client proxy errors on Render.
- Added explicit CORS allow list plus Vercel origin regex and later expanded to allow preflight OPTIONS.
- Added support for HEAD on health check so uptime monitors do not fail.
- Added runtime pin for Render using python 3.11.9.

Frontend:
- Added answer cards with Answer, Evidence, Insight, Coverage sections.
- Added Explain simply and Key takeaways buttons.
- Added copy report and show SQL actions.
- Added follow up suggestions with dedupe and a single Next best step UX.
- Added animated thinking indicator during LLM calls.
- Added highlight nodes behavior with red green strobe, moving dashed edges, and auto zoom to result set.
- Fixed graph crash from undefined coordinates and improved hover and selection styling.

Deployment:
- Deployed backend to Render and frontend to Vercel.
- Fixed CORS errors by aligning FRONTEND_URL and FRONTEND_URLS.
- Documented environment variables and rebuild behavior.

Repository hygiene:
- Created root C:\Users\dheer\Downloads\dodge-fde\README.md and updated content for final submission.
- Added C:\Users\dheer\Downloads\dodge-fde\.gitignore.
- Added AI logs folder for submission artifacts.

### Notable Errors Resolved
- Groq model decommission error by switching default model.
- Render build failures from pandas on unsupported Python version by pinning runtime.
- CORS preflight failures on Render by allowing OPTIONS and multiple frontend origins.
- Uptime monitor 405 by enabling HEAD on health endpoint.

### Session Stats
- Major iterations: 10 plus
- Features added: 12 plus
- Deployment issues resolved: 6

## Deliverable Files for Submission
- C:\Users\dheer\Downloads\dodge-fde\ai-logs\ai-session-final.md
- C:\Users\dheer\Downloads\dodge-fde\README.md
- C:\Users\dheer\Downloads\dodge-fde\.gitignore
