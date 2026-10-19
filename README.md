# AI Tech Consultant

**Why this exists:** Software code now costs 90% less to write than two years ago, so a consulting agency must handle 10x to 20x more client projects to pay the same salaries. The bottleneck is no longer writing code—it is knowing the product inside out, replying to every customer email accurately, and turning messy client meetings into clear scopes of work without losing money on unquoted scope creep.

This repository contains **one connected system made of three Python services**:

| Task | Folder | Port | What it does |
| :--- | :--- | :---: | :--- |
| **1. The Knowledge Brain** | `task1-knowledge-brain/` | `:8001` | Politely crawls the **Brilliant Directories Solution Center** sitemap, reads screenshots with Gemini Vision, answers product questions with citations, tracks daily updates/deletions, and learns from human expert escalations. |
| **2. The Inbox Agent** | `task2-inbox-agent/` | `:8002` | Reads 50 realistic customer emails across 7 categories, calls Task 1's HTTP API (`POST /query`), drafts safe replies, learns reusable rules from human edits (with Undo), and unlocks auto-send after **20 unchanged approvals in a row** for safe categories. |
| **3. Meeting to Scope of Work** | `task3-meeting-to-scope/` | `:8003` | Runs a 5-agent team on client meeting transcripts, calls Task 1's API to separate cheap built-in settings from custom code, generates 3-point hour estimates and a proposal, compares follow-up meetings against the approved baseline, and blocks sending until a human approves. |

---

## Quick Start (One-Command Run)

### 1. Prerequisites
- Python 3.11+
- A Google Gemini API key (optional for local offline testing; required for live Gemini calls)

### 2. Install & Configure
```powershell
cd D:/MyProjects/ai-tech-consultant
pip install -r requirements.txt
copy .env.example .env
# Edit .env and paste your GEMINI_API_KEY
```

### 3. Start the Entire Project with One Command
```powershell
python run_all.py
```
This starts all three services and opens the browser:
- **Screen 1 (Knowledge Brain Chat & Escalations):** `http://127.0.0.1:8001`
- **Screen 2 (Inbox Agent & 20-Streak Tracker):** `http://127.0.0.1:8002`
- **Screen 3 (Meeting to Scope & Follow-Up Diff):** `http://127.0.0.1:8003`

---

## Running Tests & Evaluations

Run the automated unit tests (`pytest`):
```powershell
pytest task1-knowledge-brain/test_task1.py task2-inbox-agent/test_task2.py task3-meeting-to-scope/test_task3.py
```

Run all **70 evaluation cases** (25 Knowledge Brain + 25 Inbox Agent + 20 Meeting-to-Scope) comparing `gemini-2.5-flash-lite` vs `gemini-2.5-flash` and saving CSV reports:
```powershell
python run_all.py --eval
```

---

## Supporting Documents
- **[DESIGN.md](./DESIGN.md)** — Business problem, architecture diagram, agent handoffs, dropped features, and failure modes.
- **[EVALS.md](./EVALS.md)** — 70 test cases across all 3 tasks comparing models on quality, cost ($ and ₹), and speed.
- **[AI_LOG.md](./AI_LOG.md)** — Our 5 most useful coding assistant prompts and 1 rejected AI suggestion.
