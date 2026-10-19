# AI_LOG.md — Coding Assistant Prompts, Real Debugging Stories & Mistakes

This document details the exact prompts given to the AI coding assistant, what broke or hallucinated during development and the real debugging steps taken to make the system production-ready.

---

## 5 Most Useful Prompts Given to the AI Coding Assistant

### 1. Designing the Shared Knowledge Brain API Contract First
> **Prompt:** *"Before writing any Task 2 or Task 3 code, design the FastAPI `/query` and `/escalations/{id}/resolve` JSON schemas in `knowledge-brain/main.py`. Make sure the response explicitly separates `status` (`answered` vs `insufficient_evidence` vs `rejected_unsafe`), `sources` (with `title`, `url`, `image_url`, and `relevance`), and `needs_human` so Task 2 and Task 3 never have to guess whether the Knowledge Brain actually knew the answer."*
- **Why it helped:** Locking the HTTP contract first prevented tight coupling. Both Task 2 (`agent.py`) and Task 3 (`agents.py`) were built against `POST http://127.0.0.1:8001/query` without importing a single internal file from Task 1.

### 2. Indexing Screenshot Details Alongside Article Text
> **Prompt:** *"In `knowledge-brain/image_reader.py` and `crawler.py`, extract UI labels, button names, and red callout boxes from help center screenshots using Gemini Vision (`ScreenshotDescriptionSchema`), and append `[SCREENSHOT DETAILS ...]` directly to the parent section chunk before embedding. Include an `is_unclear` boolean so blurry images never produce invented setting names."*
- **Why it helped:** Allowed the hybrid search engine in `search.py` to answer screenshot-only questions (like the `300px by 80px` logo dimension and `force_ssl_checkout` toggle) using the exact same retrieval path as article text.

### 3. Implementing the 20-Consecutive-Unchanged Rule with Financial Safety Blocks
> **Prompt:** *"Write `inbox-agent/autonomy.py` using SQLite so that `consecutive_unchanged` only increments when `normalize_text(generated_draft) == normalize_text(final_sent_reply)` and the human clicks Approve. Reset the counter to 0 on any edit or rejection. Add a hard policy block (`HIGH_RISK_BLOCKED_CATEGORIES`) so `refund_or_cancellation`, `complaint`, `quote_request`, and `project_request` never auto-send even if they hit 20/20."*
- **Why it helped:** Turned a vague rule into an auditable state machine that protects the business from accidentally auto-approving a $1,450 refund or a fixed-price custom code quote.

### 4. Building the 5-Agent Meeting-to-Scope Pipeline in Plain Python
> **Prompt:** *"Implement the 5 agents in `meeting-to-scope/agents.py` as 5 sequential functions (`agent_1_extract_requirements` -> `agent_2_check_feasibility` -> `agent_3_generate_scope` -> `agent_4_estimate_hours` -> `agent_5_generate_proposal` & `agent_5_compare_followup`). Have Agent 2 call Task 1's `/query` endpoint for every requirement so built-in Brilliant Directories settings get estimated at 1–3.5 hours instead of 16+ hours of custom development."*
- **Why it helped:** Kept each agent's responsibility crystal clear and saved the simulated client thousands of dollars by catching built-in search filters and CSV importers automatically.

### 5. Comparing Follow-Up Meetings Against the Approved Baseline Only
> **Prompt:** *"In `run_meeting_to_scope_pipeline`, query SQLite for the latest version where `is_approved = 1` before running `agent_5_compare_followup`. Categorize every difference into `ADDED`, `MODIFIED`, `REMOVED`, or `OUT_OF_SCOPE`, and block `POST /send/{project_id}/{version}` with HTTP 403 unless a human has approved that version."*
- **Why it helped:** Prevented unapproved AI drafts from becoming accidental commercial commitments and caught the follow-up meeting's Texas Medical Board API request as Out-of-Scope extra work.

## Architectural Suggestion We Rejected (and Why)

### What the AI Suggested
Early in planning, the AI suggested deploying a **Dockerized PostgreSQL + `pgvector` cluster, Redis Celery workers for the crawler, LangChain/CrewAI agent frameworks, and a separate Next.js/React frontend**.

### Why We Rejected It
1. **Unnecessary Moving Parts for a Small Business Tool:** Running Redis, Celery, Postgres, and Node.js build pipelines adds 4+ external points of failure that do not improve answer accuracy or scope diffing.
2. **Live-Review Explainability:** In a 30-minute live review where we must explain every line of code to the examiner and make a live modification on the spot, framework magic (like LangChain abstraction chains) makes live debugging difficult.
3. **What We Built Instead:** We replaced external vector databases and frameworks with **built-in `sqlite3` + a 20-line NumPy cosine similarity + keyword hybrid search (`search.py`)** and **5 plain Python functions (`agents.py`)**. The entire 3-task system starts with one command (`python run_all.py`), requires zero background daemons, and is 100% transparent and explainable.
