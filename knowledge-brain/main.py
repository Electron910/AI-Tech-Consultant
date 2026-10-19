"""
task1-knowledge-brain/main.py
-----------------------------
Why this file exists:
Exposes the Knowledge Brain over a clean HTTP API (Port 8001) so Task 2 (Inbox Agent)
and Task 3 (Meeting to Scope) can query product facts without copying any code.
Also serves Screen 1: the Knowledge Chat & Human Escalation UI.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from crawler import activate_article, crawl_sitemap, deactivate_article, seed_initial_knowledge_base
from search import answer_question, get_db, init_db, resolve_escalation

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """On startup, initialize SQLite tables and make sure seed articles are indexed."""
    init_db()
    seed_initial_knowledge_base()
    yield

app = FastAPI(
    title="Task 1 — The Knowledge Brain API",
    description="Shared product memory and RAG API built from the Brilliant Directories Solution Center.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=2, description="Product or support question to answer")
    model: str | None = Field(default=None, description="Optional Gemini model override (e.g., gemini-2.5-flash-lite)")
    prompt_version: str = Field(default="v2", description="Prompt version ('v1' or 'v2')")
    search_mode: str = Field(default="hybrid", description="'hybrid', 'vector', or 'keyword'")
    top_k: int = Field(default=4, ge=1, le=10)

class IngestRequest(BaseModel):
    max_pages: int = Field(default=5, ge=0, le=100, description="Max live sitemap pages to fetch in this batch")
    delay_seconds: float = Field(default=0.8, ge=0.1, le=10.0, description="Polite delay between requests")
    analyze_images: bool = Field(default=False, description="Whether to run live Gemini Vision on newly discovered images")

class ResolveEscalationRequest(BaseModel):
    expert_answer: str = Field(..., min_length=5, description="Verified answer from human specialist")
    expert_author: str = Field(default="Senior Product Specialist")
    is_global_fact: bool = Field(default=True, description="If True, saves answer into Knowledge Brain memory for future queries")

class DeactivateRequest(BaseModel):
    url: str = Field(..., description="Article URL to mark as removed from the help center")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "task1-knowledge-brain"}

@app.post("/query")
def query_knowledge_brain(req: QueryRequest):
    """Main endpoint called by the Chat UI, Task 2 (Inbox Agent), and Task 3 (Meeting to Scope)."""
    return answer_question(
        question=req.question,
        model_name=req.model,
        prompt_version=req.prompt_version,
        search_mode=req.search_mode,
        top_k=req.top_k,
    )

@app.post("/ingestion/run")
def run_ingestion(req: IngestRequest):
    """Triggers a polite sitemap crawl and daily change check."""
    return crawl_sitemap(
        max_pages=req.max_pages,
        delay_seconds=req.delay_seconds,
        analyze_images=req.analyze_images,
    )

@app.get("/ingestion/status")
def ingestion_status():
    """Returns counts of indexed articles, chunks, open escalations, and recent sync logs."""
    with get_db() as conn:
        active_articles = conn.execute("SELECT COUNT(*) AS c FROM articles WHERE is_active = 1").fetchone()["c"]
        removed_articles = conn.execute("SELECT COUNT(*) AS c FROM articles WHERE is_active = 0").fetchone()["c"]
        active_chunks = conn.execute("SELECT COUNT(*) AS c FROM chunks WHERE is_active = 1").fetchone()["c"]
        open_escalations = conn.execute("SELECT COUNT(*) AS c FROM escalations WHERE status = 'open'").fetchone()["c"]
        reports = [
            dict(r)
            for r in conn.execute("SELECT * FROM sync_reports ORDER BY id DESC LIMIT 5").fetchall()
        ]
        articles = [
            dict(r)
            for r in conn.execute(
                "SELECT url, title, category, folder, is_active, updated_at FROM articles ORDER BY is_active DESC, title ASC"
            ).fetchall()
        ]
    return {
        "active_articles": active_articles,
        "removed_articles": removed_articles,
        "active_chunks": active_chunks,
        "open_escalations": open_escalations,
        "recent_sync_reports": reports,
        "articles": articles,
    }

@app.post("/articles/deactivate")
def remove_article_endpoint(req: DeactivateRequest):
    """Marks an article as removed so it stops appearing in answers."""
    return deactivate_article(req.url)

@app.post("/articles/activate")
def activate_article_endpoint(req: DeactivateRequest):
    """Restores an article so it appears in answers again."""
    return activate_article(req.url)

@app.get("/escalations")
def list_escalations():
    """Lists all unanswered questions escalated to human experts."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM escalations ORDER BY id DESC").fetchall()
    return {"escalations": [dict(r) for r in rows]}

@app.post("/escalations/{escalation_id}/resolve")
def resolve_escalation_endpoint(escalation_id: int, req: ResolveEscalationRequest):
    """Saves a human expert's answer and adds it to the Knowledge Brain's memory."""
    try:
        return resolve_escalation(
            escalation_id=escalation_id,
            expert_answer=req.expert_answer,
            expert_author=req.expert_author,
            is_global_fact=req.is_global_fact,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.get("/", response_class=HTMLResponse)
def knowledge_brain_ui():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>AI Tech Consultant — The Knowledge Brain</title>
  <style>
    @keyframes fadeInUp {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    * { box-sizing: border-box; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; }
    body { margin: 0; background: #f1f5f9; color: #0f172a; font-size: 15.5px; line-height: 1.6; }
    header {
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      color: white;
      padding: 16px 32px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      box-shadow: 0 3px 12px rgba(15, 23, 42, 0.16);
      position: sticky;
      top: 0;
      z-index: 50;
    }
    header h1 { margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.01em; }
    nav { display: flex; gap: 10px; align-items: center; }
    nav a {
      color: #cbd5e1;
      text-decoration: none;
      font-size: 15px;
      font-weight: 600;
      padding: 8px 15px;
      border-radius: 8px;
      transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1);
    }
    nav a.active, nav a:hover {
      background: #2563eb;
      color: white;
      box-shadow: 0 4px 12px rgba(37, 99, 235, 0.35);
      transform: translateY(-1px);
    }
    .container {
      max-width: 1280px;
      margin: 28px auto;
      padding: 0 24px;
      display: grid;
      grid-template-columns: 1.35fr 1fr;
      gap: 24px;
      align-items: start;
    }
    .card {
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
      animation: fadeInUp 0.35s ease-out both;
    }
    h2 { margin-top: 0; margin-bottom: 14px; font-size: 19px; font-weight: 700; color: #0f172a; }
    label { display: block; font-size: 14.5px; font-weight: 600; color: #334155; margin-bottom: 8px; }
    textarea, input, select {
      display: block;
      width: 100%;
      padding: 12px 14px;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      font-size: 15px;
      color: #0f172a;
      background: #ffffff;
      margin-bottom: 14px;
      resize: vertical;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    textarea:focus, input:focus, select:focus {
      outline: none;
      border-color: #2563eb;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
    }
    button {
      background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
      color: white;
      border: none;
      padding: 11px 20px;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 600;
      font-size: 14.5px;
      box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25);
      transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1);
    }
    button:hover {
      background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%);
      transform: translateY(-2px);
      box-shadow: 0 6px 14px rgba(37, 99, 235, 0.32);
    }
    button:active { transform: translateY(0); }
    button.secondary {
      background: linear-gradient(135deg, #475569 0%, #334155 100%);
      box-shadow: 0 2px 6px rgba(71, 85, 105, 0.2);
    }
    button.secondary:hover {
      background: linear-gradient(135deg, #334155 0%, #1e293b 100%);
      box-shadow: 0 5px 12px rgba(71, 85, 105, 0.3);
    }
    button.btn-remove {
      background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
      box-shadow: 0 2px 6px rgba(239, 68, 68, 0.25);
    }
    button.btn-remove:hover {
      background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
      box-shadow: 0 5px 12px rgba(239, 68, 68, 0.35);
    }
    button.btn-restore {
      background: linear-gradient(135deg, #10b981 0%, #059669 100%);
      box-shadow: 0 2px 6px rgba(16, 185, 129, 0.25);
    }
    button.btn-restore:hover {
      background: linear-gradient(135deg, #059669 0%, #047857 100%);
      box-shadow: 0 5px 12px rgba(16, 185, 129, 0.35);
    }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 99px;
      font-size: 13px;
      font-weight: 600;
    }
    .badge.green { background: #dcfce7; color: #166534; }
    .badge.amber { background: #fef3c7; color: #92400e; }
    .badge.red { background: #fee2e2; color: #991b1b; }
    .source-box {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      padding: 16px;
      border-radius: 10px;
      margin-top: 12px;
      font-size: 14.5px;
      animation: fadeInUp 0.25s ease-out both;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .source-box:hover {
      border-color: #cbd5e1;
      box-shadow: 0 3px 10px rgba(15, 23, 42, 0.05);
    }
    .quick-btn {
      background: #eff6ff;
      color: #1d4ed8;
      border: 1px solid #bfdbfe;
      padding: 8px 14px;
      margin: 4px 6px 4px 0;
      font-size: 13.5px;
      border-radius: 8px;
      cursor: pointer;
      box-shadow: none;
    }
    .quick-btn:hover {
      background: #dbeafe;
      color: #1e40af;
      transform: translateY(-1px);
      box-shadow: 0 3px 8px rgba(37, 99, 235, 0.14);
    }
    .scroll-box {
      max-height: 410px;
      overflow-y: auto;
      padding-right: 8px;
    }
    .scroll-box::-webkit-scrollbar { width: 7px; }
    .scroll-box::-webkit-scrollbar-track { background: #f1f5f9; border-radius: 6px; }
    .scroll-box::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 6px; }
    .scroll-box::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
  </style>
</head>
<body>
  <header>
    <h1>AI Tech Consultant — The Knowledge Brain</h1>
    <nav>
      <a href="http://127.0.0.1:8001" class="active">1. Knowledge Brain</a>
      <a href="http://127.0.0.1:8002">2. Inbox Agent</a>
      <a href="http://127.0.0.1:8003">3. Meeting to Scope</a>
      <a href="/docs" target="_blank">API Docs</a>
    </nav>
  </header>

  <div class="container">
    <div>
      <div class="card">
        <h2>Ask the Knowledge Brain (Brilliant Directories Solution Center)</h2>
        <div style="margin-bottom: 14px;">
          <span style="font-size:14px; color:#475569; font-weight:600;">Try a sample question:</span>
          <div style="margin-top:8px;">
            <button class="quick-btn" onclick="setQ('What is the recommended website logo size shown in the Design Settings screenshot?')">Logo size in screenshot</button>
            <button class="quick-btn" onclick="setQ('Why are Stripe payments succeeding but invoices stay Unpaid in Brilliant Directories?')">Stripe webhook & SSL</button>
            <button class="quick-btn" onclick="setQ('What search filters come built-in without custom coding?')">Built-in search filters</button>
            <button class="quick-btn" onclick="setQ('Does Brilliant Directories have a native Cobol mainframe connector for 1985 IBM servers?')">Unanswerable (Triggers Escalation)</button>
          </div>
        </div>
        <label for="question">Your Question:</label>
        <textarea id="question" rows="3" placeholder="Ask any question about Brilliant Directories features, settings, billing, or troubleshooting..."></textarea>
        <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:center;">
          <select id="model" style="width:auto; margin:0; flex:1; min-width:210px;">
            <option value="gemini-flash-latest">gemini-flash-latest (Main)</option>
            <option value="gemini-flash-lite-latest">gemini-flash-lite-latest (Fast/Cheap)</option>
          </select>
          <select id="prompt_version" style="width:auto; margin:0; flex:1; min-width:240px;">
            <option value="v2">Prompt v2 (Strict Grounding + Screenshot Aware)</option>
            <option value="v1">Prompt v1 (Baseline)</option>
          </select>
          <button onclick="askBrain()">Ask Knowledge Brain</button>
        </div>

        <div id="answer-area" style="margin-top:20px; display:none;">
          <div id="status-bar" style="margin-bottom:10px;"></div>
          <div id="answer-text" style="background:#f8fafc; border-left:4px solid #2563eb; padding:14px 16px; border-radius:6px; white-space:pre-wrap; font-size:15px; line-height:1.6;"></div>
          <div id="sources-list" style="margin-top:14px;"></div>
        </div>
      </div>

      <div class="card">
        <h2>Human Expert Escalation Queue (Self-Evolving Memory)</h2>
        <p style="font-size:14.5px; color:#475569; margin-top:0; margin-bottom:14px;">
          When the chatbot lacks evidence, it escalates here. Submitting an expert answer flows directly into the Knowledge Brain's memory.
        </p>
        <div id="escalations-list" class="scroll-box">Loading escalations...</div>
      </div>
    </div>

    <div>
      <div class="card">
        <h2>Daily Sitemap Sync & Memory Status</h2>
        <div id="stats-box" style="font-size:15px; margin-bottom:16px; line-height:1.7;">Loading status...</div>
        <button onclick="runSync()" id="sync-btn">Run Polite Sitemap Sync Now</button>
        <div id="sync-result" style="margin-top:12px; font-size:14.5px; font-weight:600; color:#166534;"></div>
      </div>

      <div class="card">
        <h2>Indexed Help Articles (Test Daily Update / Removal)</h2>
        <p style="font-size:14.5px; color:#64748b; margin-top:0; margin-bottom:12px;">
          Click "Simulate Removal" on any article to verify that removed pages immediately stop appearing in answers.
        </p>
        <div id="articles-list" class="scroll-box" style="font-size:14.5px;"></div>
      </div>
    </div>
  </div>

  <script>
    function setQ(text) {
      document.getElementById('question').value = text;
      askBrain();
    }

    async function askBrain() {
      const question = document.getElementById('question').value.trim();
      if (!question) return;
      const model = document.getElementById('model').value;
      const prompt_version = document.getElementById('prompt_version').value;
      const area = document.getElementById('answer-area');
      area.style.display = 'block';
      document.getElementById('answer-text').innerText = 'Searching articles & screenshots...';

      const res = await fetch('/query', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({question, model, prompt_version})
      });
      const data = await res.json();

      const badgeClass = data.status === 'answered' ? 'green' : 'amber';
      document.getElementById('status-bar').innerHTML =
        `<span class="badge ${badgeClass}">${data.status.toUpperCase()}</span> ` +
        `<span style="font-size:14px; color:#475569; margin-left:10px;">Confidence: <strong>${data.confidence}</strong> &nbsp;|&nbsp; Latency: <strong>${data.latency_ms}ms</strong> &nbsp;|&nbsp; Cost: <strong>$${data.cost_usd}</strong></span>`;

      document.getElementById('answer-text').innerText = data.answer;

      let srcHtml = '';
      if (data.sources && data.sources.length > 0) {
        srcHtml += '<strong style="font-size:15px;">Cited Sources:</strong>';
        for (const s of data.sources) {
          srcHtml += `<div class="source-box">📄 <strong>${s.title}</strong> (Relevance: ${s.relevance})<br/><a href="${s.url}" target="_blank" style="color:#2563eb; word-break:break-all;">${s.url}</a>` +
            (s.image_url ? `<br/>🖼️ Screenshot: <code>${s.image_url}</code>` : '') + `</div>`;
        }
      }
      if (data.needs_human) {
        srcHtml += `<div class="source-box" style="background:#fef3c7; border-color:#fde68a;">⚠️ Escalated to Human Expert (Ticket #${data.escalation_id}). Resolve it below to teach the Brain!</div>`;
      }
      document.getElementById('sources-list').innerHTML = srcHtml;
      loadStatus();
      loadEscalations();
    }

    async function loadStatus() {
      const res = await fetch('/ingestion/status');
      const data = await res.json();
      document.getElementById('stats-box').innerHTML =
        `<strong>Active Articles:</strong> ${data.active_articles} &nbsp;|&nbsp; ` +
        `<strong>Active Chunks:</strong> ${data.active_chunks} &nbsp;|&nbsp; ` +
        `<strong>Removed:</strong> ${data.removed_articles} &nbsp;|&nbsp; ` +
        `<strong>Open Escalations:</strong> ${data.open_escalations}`;

      let artHtml = '';
      for (const a of data.articles) {
        const badge = a.is_active ? '<span class="badge green">Active</span>' : '<span class="badge red">Removed</span>';
        const btn = a.is_active
          ? `<button class="btn-remove" style="padding:7px 13px; font-size:13px;" onclick="removeArt('${a.url}')">Simulate Removal</button>`
          : `<button class="btn-restore" style="padding:7px 13px; font-size:13px;" onclick="restoreArt('${a.url}')">Restore Article</button>`;
        artHtml += `<div style="padding:12px 0; border-bottom:1px solid #e2e8f0; display:flex; justify-content:space-between; align-items:center; gap:12px;">
          <div>${badge} <strong style="margin-left:6px;">${a.title}</strong><br/><span style="color:#64748b; font-size:13.5px;">${a.category} &rarr; ${a.folder}</span></div>
          <div style="flex-shrink:0;">${btn}</div>
        </div>`;
      }
      document.getElementById('articles-list').innerHTML = artHtml;
    }

    async function removeArt(url) {
      await fetch('/articles/deactivate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url})
      });
      loadStatus();
    }

    async function restoreArt(url) {
      await fetch('/articles/activate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url})
      });
      loadStatus();
    }

    async function runSync() {
      const btn = document.getElementById('sync-btn');
      btn.disabled = true;
      btn.innerText = 'Syncing Sitemap Politely...';
      const res = await fetch('/ingestion/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({max_pages: 3, delay_seconds: 0.5})
      });
      const data = await res.json();
      btn.disabled = false;
      btn.innerText = 'Run Polite Sitemap Sync Now';
      document.getElementById('sync-result').innerText =
        `Sync complete — Added: ${data.added}, Updated: ${data.updated}, Unchanged: ${data.unchanged}, Removed: ${data.removed}`;
      loadStatus();
    }

    async function loadEscalations() {
      const res = await fetch('/escalations');
      const data = await res.json();
      if (!data.escalations.length) {
        document.getElementById('escalations-list').innerHTML = '<span style="color:#64748b; font-size:14.5px;">No escalations yet. Ask an unanswerable question above to create one!</span>';
        return;
      }
      let html = '';
      for (const e of data.escalations) {
        const isResolved = e.status === 'resolved';
        html += `<div class="source-box" style="margin-bottom:12px;">
          <div style="margin-bottom:6px;">
            <span class="badge ${isResolved ? 'green' : 'amber'}">#${e.id} ${e.status.toUpperCase()}</span>
            <strong style="margin-left:8px; font-size:15px;">${e.question}</strong>
          </div>
          <div style="font-size:13.5px; color:#64748b; margin-bottom:10px;">Reason: ${e.reason}</div>
          ${isResolved
            ? `<div style="margin-top:8px; color:#166534; font-size:14.5px;"><strong>Verified Expert Answer:</strong> ${e.expert_answer}</div>`
            : `<div style="margin-top:10px;">
                <input id="exp-ans-${e.id}" placeholder="Type verified product answer to teach the Knowledge Brain..." style="margin-bottom:10px;" />
                <button onclick="resolveEsc(${e.id})">Save Answer to Memory</button>
               </div>`
          }
        </div>`;
      }
      document.getElementById('escalations-list').innerHTML = html;
    }

    async function resolveEsc(id) {
      const val = document.getElementById('exp-ans-' + id).value.trim();
      if (!val) return;
      await fetch(`/escalations/${id}/resolve`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({expert_answer: val, is_global_fact: true})
      });
      loadEscalations();
      loadStatus();
    }

    loadStatus();
    loadEscalations();
  </script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
