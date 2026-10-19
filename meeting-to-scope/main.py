"""
task3-meeting-to-scope/main.py
------------------------------
Why this file exists:
Exposes the Meeting-to-Scope multi-agent pipeline on Port 8003 and serves Screen 3:
Transcript selector, 5-Agent Scope & Hour Estimate Builder, Follow-Up Change Diff,
and Human Approval Gate.
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from agents import (
    approve_scope_version,
    get_db,
    init_scope_db,
    run_meeting_to_scope_pipeline,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_scope_db()
    yield

app = FastAPI(
    title="Task 3 — Meeting to Scope of Work API",
    description="Multi-agent pipeline turning client meeting transcripts into a Scope of Work, Hour Estimates, Client Proposal, and Follow-Up Change Report.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class GenerateScopeRequest(BaseModel):
    project_id: str = Field(default="PROJ-CARECONNECT", description="Project identifier (links follow-up meetings to baseline)")
    transcript_name: str = Field(default="meeting_1_search.txt")
    transcript_text: str = Field(..., min_length=20)
    hourly_rate_usd: float = Field(default=100.0, ge=10.0, le=1000.0)
    model: str | None = None
    prompt_version: str = Field(default="v2")

class ApproveRequest(BaseModel):
    project_id: str
    version: int
    reviewer_name: str = Field(default="Senior Partner")

@app.get("/health")
def health():
    return {"status": "ok", "service": "task3-meeting-to-scope"}

@app.get("/transcripts")
def list_transcripts():
    """Returns the 3 role-played meeting transcripts."""
    items = [
        {
            "filename": "meeting_1_search.txt",
            "label": "Meeting A — CareConnect Medical Directory (Initial Search & Mobile Scope)",
            "project_id": "PROJ-CARECONNECT",
        },
        {
            "filename": "meeting_2_checkout.txt",
            "label": "Meeting B — BuildPro Marketplace (Checkout, Twilio Alerts & Gateways)",
            "project_id": "PROJ-BUILDPRO",
        },
        {
            "filename": "meeting_3_followup.txt",
            "label": "Meeting C — CareConnect Follow-Up (Updates Meeting A Baseline + Scope Creep!)",
            "project_id": "PROJ-CARECONNECT",
        },
    ]
    out = []
    for it in items:
        p = TRANSCRIPTS_DIR / it["filename"]
        out.append({**it, "text": p.read_text(encoding="utf-8") if p.exists() else ""})
    return {"transcripts": out}

@app.post("/generate")
def generate_scope_endpoint(req: GenerateScopeRequest):
    """Runs the 5-agent team on a meeting transcript."""
    return run_meeting_to_scope_pipeline(
        project_id=req.project_id,
        transcript_name=req.transcript_name,
        transcript_text=req.transcript_text,
        hourly_rate_usd=req.hourly_rate_usd,
        model_name=req.model,
        prompt_version=req.prompt_version,
    )

@app.post("/approve")
def approve_scope_endpoint(req: ApproveRequest):
    """Approves a scope version so it can be sent to the client and serves as the baseline for follow-ups."""
    try:
        return approve_scope_version(req.project_id, req.version, req.reviewer_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/send/{project_id}/{version}")
def send_proposal_to_client(project_id: str, version: int):
    """Enforces the rule: Nothing reaches the client until a human approves it!"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT is_approved, approved_by FROM scope_versions WHERE project_id = ? AND version = ?",
            (project_id, version),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Version not found")
    if not row["is_approved"]:
        raise HTTPException(
            status_code=403,
            detail="BLOCKED: Unapproved proposals cannot be sent to the client. A human reviewer must approve this version first.",
        )
    return {
        "status": "sent_to_client",
        "project_id": project_id,
        "version": version,
        "approved_by": row["approved_by"],
    }

@app.get("/", response_class=HTMLResponse)
def scope_builder_ui():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>AI Tech Consultant — Meeting to Scope of Work</title>
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
      max-width: 1320px;
      margin: 28px auto;
      padding: 0 24px;
      display: grid;
      grid-template-columns: 400px 1fr;
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
    label {
      display: block;
      width: 100%;
      font-size: 14.5px;
      font-weight: 600;
      color: #334155;
      margin-bottom: 8px;
    }
    textarea, select, input {
      display: block;
      width: 100%;
      padding: 12px 14px;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      font-size: 15px;
      line-height: 1.55;
      color: #0f172a;
      background: #ffffff;
      margin-bottom: 16px;
      resize: vertical;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    textarea:focus, select:focus, input:focus {
      outline: none;
      border-color: #2563eb;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
    }
    button {
      background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
      color: white;
      border: none;
      padding: 12px 20px;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 600;
      font-size: 14.5px;
      box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25);
      transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1);
    }
    button:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 14px rgba(15, 23, 42, 0.18);
    }
    button:active { transform: translateY(0); }
    button.green {
      background: linear-gradient(135deg, #16a34a 0%, #15803d 100%);
      box-shadow: 0 2px 6px rgba(22, 163, 74, 0.25);
    }
    button.green:hover { background: linear-gradient(135deg, #15803d 0%, #166534 100%); }
    button.amber {
      background: linear-gradient(135deg, #d97706 0%, #b45309 100%);
      box-shadow: 0 2px 6px rgba(217, 119, 6, 0.25);
    }
    button.amber:hover { background: linear-gradient(135deg, #b45309 0%, #92400e 100%); }
    .banner-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 20px;
      flex-wrap: wrap;
    }
    .banner-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      flex-shrink: 0;
    }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 99px;
      font-size: 12.5px;
      font-weight: 600;
      margin-bottom: 4px;
    }
    .badge.existing_configuration, .badge.ADDED { background: #dcfce7; color: #166534; }
    .badge.custom_development, .badge.MODIFIED { background: #fef3c7; color: #92400e; }
    .badge.needs_clarification, .badge.OUT_OF_SCOPE, .badge.REMOVED { background: #fee2e2; color: #991b1b; }
    table { width: 100%; border-collapse: collapse; font-size: 14.5px; margin-top: 10px; }
    th, td { text-align: left; padding: 12px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; line-height: 1.55; }
    th { background: #f8fafc; color: #334155; font-weight: 700; }
    pre {
      white-space: pre-wrap;
      background: #f8fafc;
      padding: 18px;
      border-radius: 10px;
      border: 1px solid #e2e8f0;
      font-size: 14.5px;
      line-height: 1.65;
      max-height: 460px;
      overflow-y: auto;
    }
  </style>
</head>
<body>
  <header>
    <h1>AI Tech Consultant — Meeting to Scope of Work</h1>
    <nav>
      <a href="http://127.0.0.1:8001">1. Knowledge Brain</a>
      <a href="http://127.0.0.1:8002">2. Inbox Agent</a>
      <a href="http://127.0.0.1:8003" class="active">3. Meeting to Scope</a>
      <a href="/docs" target="_blank">API Docs</a>
    </nav>
  </header>

  <div class="container">
    <div>
      <div class="card">
        <h2>Step 1: Choose Role-Played Meeting Transcript</h2>
        <label for="transcript-select">Select Meeting Scenario:</label>
        <select id="transcript-select" onchange="pickTranscript()"></select>
        <label for="project-id">Project ID (links Follow-up Meeting C to Meeting A):</label>
        <input id="project-id" value="PROJ-CARECONNECT" />
        <label for="hourly-rate">Configurable Hourly Rate ($ USD):</label>
        <input id="hourly-rate" type="number" value="100" />
        <label for="transcript-text">Meeting Transcript:</label>
        <textarea id="transcript-text" rows="13"></textarea>
        <button onclick="runPipeline()" id="run-btn" style="width:100%;">Run 5-Agent Scope & Estimate Pipeline</button>
      </div>
    </div>

    <div>
      <div class="card" id="approval-banner" style="display:none; background:#fffbeb; border-color:#fde68a;">
        <div class="banner-row">
          <div style="flex:1; min-width:260px;">
            <strong id="approval-title" style="font-size:16.5px;">🔒 Draft Pending Human Approval</strong>
            <div style="font-size:14px; color:#92400e; margin-top:4px;" id="approval-sub">
              Approve Meeting A first so it becomes the official Baseline, then run Meeting C to see the Follow-Up Change Report!
            </div>
          </div>
          <div class="banner-actions">
            <button class="green" onclick="approveCurrent()">Approve Scope Baseline</button>
            <button class="amber" onclick="trySendClient()">Send Proposal to Client</button>
          </div>
        </div>
        <div id="send-msg" style="margin-top:12px; font-size:14.5px; font-weight:600;"></div>
      </div>

      <div class="card" id="diff-card" style="display:none; border:2px solid #2563eb;">
        <h2>Follow-Up Meeting Change Report (Compared Against Approved Baseline)</h2>
        <div id="diff-summary" style="font-size:15px; margin-bottom:12px;"></div>
        <div id="diff-table"></div>
      </div>

      <div class="card">
        <h2>Extracted Requirements & Feasibility Check (Built-in vs Custom Code)</h2>
        <div id="reqs-table" style="font-size:15px; color:#475569;">Run the pipeline on the left to extract requirements and check built-in Brilliant Directories settings via the Knowledge Brain API.</div>
      </div>

      <div class="card">
        <h2>Developer Task Breakdown & 3-Point Hour Estimates</h2>
        <div id="estimates-table" style="font-size:15px; color:#475569;">Hour estimates will appear here...</div>
      </div>

      <div class="card">
        <h2>Client-Ready Proposal Preview</h2>
        <pre id="proposal-preview">Proposal will appear here...</pre>
      </div>
    </div>
  </div>

  <script>
    let transcripts = [];
    let currentResult = null;

    async function loadTranscripts() {
      const res = await fetch('/transcripts');
      const data = await res.json();
      transcripts = data.transcripts;
      const sel = document.getElementById('transcript-select');
      sel.innerHTML = transcripts.map((t, i) => `<option value="${i}">${t.label}</option>`).join('');
      pickTranscript();
    }

    function pickTranscript() {
      const idx = document.getElementById('transcript-select').value;
      const t = transcripts[idx];
      document.getElementById('project-id').value = t.project_id;
      document.getElementById('transcript-text').value = t.text;
    }

    async function runPipeline() {
      const idx = document.getElementById('transcript-select').value;
      const t = transcripts[idx];
      const btn = document.getElementById('run-btn');
      btn.disabled = true;
      btn.innerText = 'Running 5 Agents & Querying Knowledge Brain API...';

      const res = await fetch('/generate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          project_id: document.getElementById('project-id').value,
          transcript_name: t.filename,
          transcript_text: document.getElementById('transcript-text').value,
          hourly_rate_usd: parseFloat(document.getElementById('hourly-rate').value || '100')
        })
      });
      currentResult = await res.json();
      btn.disabled = false;
      btn.innerText = 'Run 5-Agent Scope & Estimate Pipeline';
      renderResult(currentResult);
    }

    function renderResult(r) {
      document.getElementById('approval-banner').style.display = 'block';
      document.getElementById('approval-title').innerText =
        `🔒 Project ${r.project_id} — Version v${r.version} (Pending Human Approval)`;
      document.getElementById('send-msg').innerText = '';

      // Follow-up diff card
      const diffCard = document.getElementById('diff-card');
      if (r.change_report) {
        diffCard.style.display = 'block';
        const cr = r.change_report;
        document.getElementById('diff-summary').innerHTML =
          `<strong>Deadline Change:</strong> ${cr.baseline_deadline} &rarr; <strong>${cr.revised_deadline}</strong> &nbsp;|&nbsp; ` +
          `<strong>Baseline Hours:</strong> ${cr.baseline_total_likely_hours}h &rarr; <strong>Revised:</strong> ${cr.revised_total_likely_hours}h ` +
          `(Net Delta: ${cr.net_delta_hours >= 0 ? '+' : ''}${cr.net_delta_hours}h | <strong>Out-of-Scope Extra Quote: +${cr.out_of_scope_extra_quote_hours}h</strong>)`;

        let dTbl = `<table><thead><tr><th>Req ID</th><th>Change Type</th><th>Requirement</th><th>What Changed</th><th>Hour Delta</th><th>Extra Quote?</th></tr></thead><tbody>`;
        for (const c of cr.changes) {
          dTbl += `<tr>
            <td><strong>${c.req_id}</strong></td>
            <td><span class="badge ${c.change_type}">${c.change_type}</span></td>
            <td><strong>${c.title}</strong></td>
            <td>${c.summary_of_change}</td>
            <td>${c.delta_likely_hours >= 0 ? '+' : ''}${c.delta_likely_hours}h</td>
            <td>${c.requires_extra_quote ? '⚠️ <strong>YES (Quote Extra)</strong>' : 'No'}</td>
          </tr>`;
        }
        dTbl += `</tbody></table>`;
        document.getElementById('diff-table').innerHTML = dTbl;
      } else {
        diffCard.style.display = 'none';
      }

      // Requirements & Feasibility table
      let rTbl = `<table><thead><tr><th>ID</th><th>Requirement & Transcript Quote</th><th>Status</th><th>Feasibility Result</th><th>Testable Acceptance Criteria</th></tr></thead><tbody>`;
      for (const d of r.scope.deliverables) {
        rTbl += `<tr>
          <td><strong>${d.req_id}</strong></td>
          <td><strong>${d.title}</strong><br/><span style="color:#64748b; font-size:13.5px;">${d.source_quote}</span></td>
          <td><code>${d.status}</code></td>
          <td><span class="badge ${d.feasibility_class}">${d.feasibility_class}</span><br/><span style="font-size:13.5px; color:#334155;">${d.proposed_approach}</span></td>
          <td>${d.acceptance_criteria}</td>
        </tr>`;
      }
      rTbl += `</tbody></table>`;
      document.getElementById('reqs-table').innerHTML = rTbl;

      // Estimates table
      let eTbl = `<table><thead><tr><th>Req ID</th><th>Engineering Task</th><th>Feasibility</th><th>Low</th><th>Likely</th><th>High</th><th>Assumptions</th></tr></thead><tbody>`;
      for (const t of r.estimates.tasks) {
        eTbl += `<tr>
          <td><strong>${t.req_id}</strong></td>
          <td>${t.task_name}</td>
          <td><span class="badge ${t.feasibility_class}">${t.feasibility_class}</span></td>
          <td>${t.low_hours}h</td>
          <td><strong>${t.likely_hours}h</strong></td>
          <td>${t.high_hours}h</td>
          <td>${t.assumptions}</td>
        </tr>`;
      }
      eTbl += `</tbody></table><div style="margin-top:14px; font-size:15px;"><strong>Confirmed Scope Likely Hours:</strong> ${r.estimates.confirmed_scope_likely_hours}h &nbsp;|&nbsp; <strong>Total Range (with Optional/Unclear):</strong> ${r.estimates.total_low_hours}h – <strong>${r.estimates.total_likely_hours}h</strong> – ${r.estimates.total_high_hours}h</div>`;
      document.getElementById('estimates-table').innerHTML = eTbl;

      document.getElementById('proposal-preview').innerText = r.proposal_markdown;
    }

    async function approveCurrent() {
      if (!currentResult) return;
      const res = await fetch('/approve', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          project_id: currentResult.project_id,
          version: currentResult.version,
          reviewer_name: 'Alex Rivera (Senior Consultant)'
        })
      });
      const data = await res.json();
      document.getElementById('approval-title').innerText =
        `✅ Project ${data.project_id} — Version v${data.approved_version} APPROVED Baseline`;
      document.getElementById('send-msg').style.color = '#166534';
      document.getElementById('send-msg').innerText =
        `Approved by ${data.approved_by}! You can now send to client OR select Meeting C on the left to test Follow-Up Change Detection against this baseline.`;
    }

    async function trySendClient() {
      if (!currentResult) return;
      const res = await fetch(`/send/${currentResult.project_id}/${currentResult.version}`, {method: 'POST'});
      const data = await res.json();
      const msgEl = document.getElementById('send-msg');
      if (!res.ok) {
        msgEl.style.color = '#dc2626';
        msgEl.innerText = data.detail;
      } else {
        msgEl.style.color = '#166534';
        msgEl.innerText = `🚀 Proposal v${data.version} sent to client (Approved by ${data.approved_by}).`;
      }
    }

    loadTranscripts();
  </script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8003)
