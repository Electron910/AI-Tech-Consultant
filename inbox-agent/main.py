"""
Why this file exists:
Exposes the Inbox Agent API on Port 8002 and serves Screen 2:
The Inbox Review, Human Feedback Learning, and 20-Consecutive-Approval Dashboard.
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from agent import (
    draft_email_response,
    get_active_learned_rules,
    submit_human_review,
    toggle_learned_rule,
)
from autonomy import (
    get_all_autonomy_statuses,
    get_db,
    init_autonomy_tables,
    record_human_decision,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
EMAILS_PATH = Path(__file__).parent / "emails_50.json"

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_autonomy_tables()
    yield

app = FastAPI(
    title="Task 2 — The Inbox Agent API",
    description="Reads customer emails, calls Task 1's Knowledge Brain API, drafts grounded replies, learns from human edits, and enforces the 20-streak autonomy rule.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class DraftRequest(BaseModel):
    id: str = Field(default="EM-CUSTOM")
    sender_name: str = Field(default="Alex Customer")
    sender_email: str = Field(default="alex@example.com")
    subject: str
    body: str
    model: str | None = None
    prompt_version: str = Field(default="v2")

class ReviewSubmissionRequest(BaseModel):
    email_item: dict
    draft_result: dict
    final_sent_reply: str
    outcome: str = Field(description="'approved', 'edited', or 'rejected'")
    reviewer_note: str = Field(default="")

class ToggleRuleRequest(BaseModel):
    is_active: bool

@app.get("/health")
def health():
    return {"status": "ok", "service": "task2-inbox-agent"}

@app.get("/emails")
def list_dataset_emails():
    """Returns the 50 realistic customer emails."""
    emails = json.loads(EMAILS_PATH.read_text(encoding="utf-8"))
    return {"total": len(emails), "emails": emails}

@app.post("/draft")
def generate_draft_endpoint(req: DraftRequest):
    """Calls Task 1 API and generates a grounded email draft."""
    return draft_email_response(
        email_item=req.model_dump(),
        model_name=req.model,
        prompt_version=req.prompt_version,
    )

@app.post("/review")
def submit_review_endpoint(req: ReviewSubmissionRequest):
    """Records human approval/edit/rejection, updates the 20-streak counter, and learns from edits."""
    return submit_human_review(
        email_item=req.email_item,
        draft_result=req.draft_result,
        final_sent_reply=req.final_sent_reply,
        outcome=req.outcome,
        reviewer_note=req.reviewer_note,
    )

@app.get("/autonomy")
def autonomy_status_endpoint():
    """Returns the 20-in-a-row streak counters and learned feedback rules."""
    with get_db() as conn:
        rules = [dict(r) for r in conn.execute("SELECT * FROM learned_rules ORDER BY id DESC").fetchall()]
        history = [
            dict(r)
            for r in conn.execute(
                "SELECT id, email_id, subject, predicted_category, approval_outcome, was_edited, created_at "
                "FROM email_interactions ORDER BY id DESC LIMIT 15"
            ).fetchall()
        ]
    return {
        "streaks": get_all_autonomy_statuses(),
        "learned_rules": rules,
        "recent_reviews": history,
    }

@app.post("/autonomy/simulate-20/{category}")
def simulate_twenty_approvals(category: str):
    """Helper button for live demo: simulates 20 unchanged approvals in a row for a category."""
    sample_text = "Verified unchanged reply."
    status = {}
    for _ in range(20):
        status = record_human_decision(category, sample_text, sample_text, "approved")
    return status

@app.post("/rules/{rule_id}/toggle")
def toggle_rule_endpoint(rule_id: int, req: ToggleRuleRequest):
    """Enables or disables (Undoes) a learned human feedback rule."""
    return toggle_learned_rule(rule_id, req.is_active)

@app.get("/", response_class=HTMLResponse)
def inbox_agent_ui():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>AI Tech Consultant — The Inbox Agent</title>
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
      max-width: 1300px;
      margin: 28px auto;
      padding: 0 24px;
      display: grid;
      grid-template-columns: 370px 1fr;
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
    .email-item {
      padding: 12px 14px;
      border-bottom: 1px solid #f1f5f9;
      border-radius: 8px;
      cursor: pointer;
      font-size: 14.5px;
      transition: all 0.18s ease;
    }
    .email-item:hover { background: #f8fafc; transform: translateX(2px); }
    .email-item.active {
      background: #eff6ff;
      border-left: 4px solid #2563eb;
    }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 99px;
      font-size: 12.5px;
      font-weight: 600;
    }
    .badge.low { background: #dcfce7; color: #166534; }
    .badge.moderate { background: #fef3c7; color: #92400e; }
    .badge.high { background: #fee2e2; color: #991b1b; }
    label {
      display: block;
      width: 100%;
      font-size: 14.5px;
      font-weight: 600;
      color: #1e293b;
      margin-bottom: 8px;
    }
    textarea {
      display: block;
      width: 100%;
      padding: 14px;
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      font-size: 15px;
      line-height: 1.6;
      color: #0f172a;
      background: #ffffff;
      resize: vertical;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    textarea:focus {
      outline: none;
      border-color: #2563eb;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
    }
    .action-btn-group {
      margin-top: 16px;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
    }
    .action-buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }
    button {
      background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
      color: white;
      border: none;
      padding: 11px 18px;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 600;
      font-size: 14.5px;
      box-shadow: 0 2px 6px rgba(37, 99, 235, 0.22);
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
    button.red {
      background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
      box-shadow: 0 2px 6px rgba(220, 38, 38, 0.25);
    }
    button.red:hover { background: linear-gradient(135deg, #b91c1c 0%, #991b1b 100%); }
    button.secondary {
      background: linear-gradient(135deg, #475569 0%, #334155 100%);
      font-size: 13px;
      padding: 7px 13px;
      box-shadow: 0 2px 5px rgba(71, 85, 105, 0.18);
    }
    table { width: 100%; border-collapse: collapse; font-size: 14.5px; }
    th, td { text-align: left; padding: 11px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: middle; }
    th { color: #334155; font-weight: 700; background: #f8fafc; }
    .scroll-box {
      max-height: 320px;
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
    <h1>AI Tech Consultant — The Inbox Agent</h1>
    <nav>
      <a href="http://127.0.0.1:8001">1. Knowledge Brain</a>
      <a href="http://127.0.0.1:8002" class="active">2. Inbox Agent</a>
      <a href="http://127.0.0.1:8003">3. Meeting to Scope</a>
      <a href="/docs" target="_blank">API Docs</a>
    </nav>
  </header>

  <div class="container">
    <div class="card" style="max-height: 85vh; overflow-y: auto;" class="scroll-box">
      <h2>Customer Inbox (50 Emails)</h2>
      <div id="email-list">Loading 50 emails...</div>
    </div>

    <div>
      <div class="card">
        <h2>Selected Email & AI Grounded Draft</h2>
        <div id="selected-email-box" style="background:#f8fafc; border:1px solid #e2e8f0; padding:16px; border-radius:10px; font-size:15px; margin-bottom:16px;">
          Select any email on the left to call Task 1's Knowledge Brain API and draft a reply.
        </div>

        <div id="draft-controls" style="display:none;">
          <div id="draft-meta" style="margin-bottom:12px; font-size:14.5px;"></div>
          <div id="kb-evidence" style="background:#eff6ff; border:1px solid #bfdbfe; padding:14px 16px; border-radius:10px; font-size:14.5px; margin-bottom:16px;"></div>
          <div style="width:100%;">
            <label for="draft-textarea">Draft Reply (Edit before sending to teach the agent):</label>
            <textarea id="draft-textarea" rows="8"></textarea>
          </div>
          <div class="action-btn-group">
            <div class="action-buttons">
              <button class="green" onclick="submitDecision('approved')">Approve & Send (1-Click)</button>
              <button class="amber" onclick="submitDecision('edited')">Save My Edit & Teach Agent</button>
              <button class="red" onclick="submitDecision('rejected')">Reject Draft (Reset Streak)</button>
            </div>
            <span id="review-feedback" style="font-size:14.5px; font-weight:700; color:#166534;"></span>
          </div>
        </div>
      </div>

      <div class="card">
        <h2>20-in-a-Row Unchanged Auto-Send Tracker & Safety Policy</h2>
        <p style="font-size:14.5px; color:#475569; margin-top:0; margin-bottom:14px;">
          Once humans send 20 drafts of the same category in a row without editing a single word, safe categories unlock Auto-Send. Any edit or rejection resets the streak to 0. High-risk categories (Refunds, Complaints, Quotes, Projects) remain human-reviewed by safety policy.
        </p>
        <div id="streaks-table"></div>
      </div>

      <div class="card">
        <h2>Learned Rules from Human Edits (Self-Improving Prompts with Undo)</h2>
        <div id="rules-list" class="scroll-box" style="font-size:14.5px;">No edits recorded yet. Edit a draft above and click "Save My Edit & Teach Agent"!</div>
      </div>
    </div>
  </div>

  <script>
    let allEmails = [];
    let currentEmail = null;
    let currentDraft = null;

    async function loadEmails() {
      const res = await fetch('/emails');
      const data = await res.json();
      allEmails = data.emails;
      let html = '';
      for (const e of allEmails) {
        html += `<div class="email-item" id="item-${e.id}" onclick="selectEmail('${e.id}')">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
            <span><strong>${e.id}</strong> — ${e.sender_name}</span>
            <span class="badge ${e.expected_risk}">${e.expected_category}</span>
          </div>
          <div style="color:#334155; margin-top:4px; font-weight:500;">${e.subject}</div>
        </div>`;
      }
      document.getElementById('email-list').innerHTML = html;
      if (allEmails.length > 0) selectEmail(allEmails[0].id);
    }

    async function selectEmail(id) {
      currentEmail = allEmails.find(x => x.id === id);
      document.querySelectorAll('.email-item').forEach(el => el.classList.remove('active'));
      const activeEl = document.getElementById('item-' + id);
      if (activeEl) activeEl.classList.add('active');

      document.getElementById('selected-email-box').innerHTML =
        `<strong>From:</strong> ${currentEmail.sender_name} &lt;${currentEmail.sender_email}&gt;<br/>` +
        `<strong>Subject:</strong> ${currentEmail.subject}<hr style="border:0; border-top:1px solid #e2e8f0; margin:10px 0;"/>` +
        `<div>${currentEmail.body}</div>`;

      document.getElementById('draft-controls').style.display = 'block';
      document.getElementById('draft-textarea').value = 'Calling Knowledge Brain API and drafting reply...';
      document.getElementById('review-feedback').innerText = '';

      const res = await fetch('/draft', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(currentEmail)
      });
      currentDraft = await res.json();

      const conf = currentDraft.confidence || (currentDraft.kb_status === 'answered' ? 0.95 : 0.68);
      const urg = currentDraft.urgency || 'low';
      const urgBadge = urg === 'high' ? 'red' : (urg === 'medium' ? 'amber' : 'green');
      document.getElementById('draft-meta').innerHTML =
        `<strong>Category:</strong> <code>${currentDraft.category}</code> &nbsp;|&nbsp; ` +
        `<strong>Priority:</strong> <span class="badge ${urgBadge}">${urg.toUpperCase()}</span> &nbsp;|&nbsp; ` +
        `<strong>Risk:</strong> <span class="badge ${currentDraft.risk_level}">${currentDraft.risk_level.toUpperCase()}</span> &nbsp;|&nbsp; ` +
        `<strong>Confidence:</strong> <span class="badge green">${conf}</span> &nbsp;|&nbsp; ` +
        `<strong>Knowledge Brain Status:</strong> <code>${currentDraft.kb_status}</code> &nbsp;|&nbsp; ` +
        `<strong>Auto-Send Eligible:</strong> ${currentDraft.auto_sent ? '✅ YES (Auto-Sent)' : '🔒 Requires Human Click'}`;

      let srcLinks = (currentDraft.sources || []).map(s => `<a href="${s.url}" target="_blank" style="color:#1d4ed8; font-weight:600;">${s.title}</a>`).join(', ') || 'None';
      document.getElementById('kb-evidence').innerHTML =
        `<strong>Evidence from Knowledge Brain API:</strong> ${srcLinks}<br/>` +
        `<strong>Follow-up Action:</strong> ${currentDraft.follow_up_action || 'None'}`;

      document.getElementById('draft-textarea').value = currentDraft.suggested_reply;
    }

    async function submitDecision(outcome) {
      if (!currentEmail || !currentDraft) return;
      const finalReply = document.getElementById('draft-textarea').value;
      const res = await fetch('/review', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          email_item: currentEmail,
          draft_result: currentDraft,
          final_sent_reply: finalReply,
          outcome: outcome
        })
      });
      const data = await res.json();
      let msg = `Recorded: ${data.outcome_recorded.toUpperCase()} (Streak: ${data.streak_status.progress_to_20})`;
      if (data.new_learned_rule) {
        msg += ` | New Rule Learned!`;
      }
      document.getElementById('review-feedback').innerText = msg;
      loadAutonomy();
    }

    async function sim20(cat) {
      await fetch('/autonomy/simulate-20/' + cat, {method: 'POST'});
      loadAutonomy();
    }

    async function toggleRule(id, active) {
      await fetch(`/rules/${id}/toggle`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({is_active: active})
      });
      loadAutonomy();
    }

    async function loadAutonomy() {
      const res = await fetch('/autonomy');
      const data = await res.json();

      let tbl = `<table><thead><tr><th>Category</th><th>Unchanged Streak</th><th>Approved / Edited / Rejected</th><th>Auto-Send State</th><th>Test Helper</th></tr></thead><tbody>`;
      for (const s of data.streaks) {
        let stateHtml = '🔒 Human Review';
        if (s.auto_send_enabled) {
          stateHtml = '<span class="badge low">⚡ AUTO-SEND ON (20/20)</span>';
        } else if (s.consecutive_unchanged >= 20 && s.blocked_by_safety_policy) {
          stateHtml = '<span class="badge high">🛡️ Blocked by Financial/Risk Policy</span>';
        }
        tbl += `<tr>
          <td><strong>${s.category}</strong></td>
          <td><strong>${s.progress_to_20}</strong></td>
          <td>${s.total_approved} / ${s.total_edited} / ${s.total_rejected}</td>
          <td>${stateHtml}</td>
          <td><button class="secondary" onclick="sim20('${s.category}')">Simulate 20 Streak</button></td>
        </tr>`;
      }
      tbl += `</tbody></table>`;
      document.getElementById('streaks-table').innerHTML = tbl;

      if (data.learned_rules.length > 0) {
        let rHtml = '';
        for (const r of data.learned_rules) {
          const badge = r.is_active ? '<span class="badge low">Active</span>' : '<span class="badge high">Undone / Off</span>';
          const btn = r.is_active
            ? `<button class="secondary" onclick="toggleRule(${r.id}, false)">Undo Rule</button>`
            : `<button class="secondary" onclick="toggleRule(${r.id}, true)">Re-Enable</button>`;
          rHtml += `<div style="padding:10px 0; border-bottom:1px solid #f1f5f9; display:flex; justify-content:space-between; align-items:center; gap:12px;">
            <div>${badge} <strong style="margin-left:6px;">[${r.category}]</strong> ${r.rule_text}</div>
            <div style="flex-shrink:0;">${btn}</div>
          </div>`;
        }
        document.getElementById('rules-list').innerHTML = rHtml;
      }
    }

    loadEmails();
    loadAutonomy();
  </script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
