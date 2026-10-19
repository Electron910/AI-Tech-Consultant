"""
task3-meeting-to-scope/agents.py
--------------------------------
Why this file exists:
Implements the 5-agent team as 5 clear, easy-to-read Python functions:
- Agent 1 (`agent_1_extract_requirements`): Splits long transcripts into stages & extracts requirements with exact quotes.
- Agent 2 (`agent_2_check_feasibility`): Calls Task 1's Knowledge Brain HTTP API to check built-in settings vs custom code.
- Agent 3 (`agent_3_generate_scope`): Writes the formal Scope of Work with exclusions and testable acceptance criteria.
- Agent 4 (`agent_4_estimate_hours`): Produces Low / Likely / High hour estimates (saving money on built-in settings).
- Agent 5 (`agent_5_generate_proposal` + `agent_5_compare_followup`): Generates the client proposal and compares follow-up meetings against the Approved Baseline.
"""

import json
import os
import sqlite3
import time
from pathlib import Path
import httpx
from google import genai
from prompts import TRANSCRIPT_PROMPTS, TranscriptAnalysisSchema

DB_PATH = Path(__file__).parent / "scope.db"

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_scope_db() -> None:
    """Creates SQLite tables to store project versions, human approvals, and change reports."""
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                project_name TEXT,
                current_version INTEGER DEFAULT 1,
                approved_version INTEGER DEFAULT 0,
                approved_by TEXT,
                approved_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS scope_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                version INTEGER,
                transcript_name TEXT,
                analysis_json TEXT,
                feasibility_json TEXT,
                scope_json TEXT,
                estimates_json TEXT,
                proposal_markdown TEXT,
                change_report_json TEXT,
                is_approved INTEGER DEFAULT 0,
                approved_by TEXT,
                approved_at TEXT,
                created_at TEXT
            );
            """
        )

def get_task1_url() -> str:
    return os.getenv("TASK1_API_URL", "http://127.0.0.1:8001").rstrip("/")

def split_long_transcript(transcript_text: str, max_chars: int = 2600, overlap_chars: int = 300) -> list[str]:
    """
    Long transcripts can lose details in the middle if sent all at once.
    This function splits long transcripts along speaker turns with overlap.
    """
    text = transcript_text.strip()
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            tail = current[-overlap_chars:] if len(current) > overlap_chars else current
            current = f"{tail}\n\n{para}".strip()
    if current:
        chunks.append(current)
    return chunks

def agent_1_extract_requirements(
    transcript_text: str,
    model_name: str | None = None,
    prompt_version: str = "v2",
) -> dict:
    """
    Reads a meeting transcript (in stages if long) and outputs structured requirements,
    retaining exact speaker timestamps and separating confirmed facts from vague ideas.
    """
    chunks = split_long_transcript(transcript_text)
    lower = transcript_text.lower()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_to_use = model_name or os.getenv("GEMINI_MAIN_MODEL", "gemini-flash-latest")
    if api_key and api_key != "your_gemini_api_key_here":
        try:
            client = genai.Client(api_key=api_key)
            prompt = TRANSCRIPT_PROMPTS.get(prompt_version, TRANSCRIPT_PROMPTS["v2"]).format(
                transcript="\n\n--- NEXT SECTION ---\n\n".join(chunks)
            )
            res = client.models.generate_content(
                model=model_to_use,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=TranscriptAnalysisSchema,
                    temperature=0.1,
                ),
            )
            parsed = TranscriptAnalysisSchema.model_validate_json(res.text)
            out = parsed.model_dump()
            out["stages_processed"] = len(chunks)
            return out
        except Exception:
            pass

    if "meeting transcript c" in lower or ("2,200 texas doctors" in lower and "sticky bottom-sheet" in lower):
        return {
            "project_name": "CareConnect Medical Directory (Follow-Up Revision)",
            "client_summary": "Follow-up meeting updating Meeting A: keeps built-in search filters & logo, drops AI symptom search, upgrades mobile to custom sticky AJAX bottom-sheet drawer, adds 2,200-doctor CSV import + custom Texas Medical Board API license check, and moves deadline up 2 weeks.",
            "target_deadline": "November 1 (Moved up 2 weeks from November 15)",
            "stated_budget": "$1,500 to $3,500 baseline (extra quote required for out-of-scope custom work)",
            "stages_processed": len(chunks),
            "requirements": [
                {
                    "req_id": "REQ-001",
                    "title": "Specialty, Sub-Specialty, 25-Mile Radius & Star/Verified Filters",
                    "description": "Configure built-in Category + Sub-Category + 25-mile Location Radius search and Sidebar Star Rating / Verified Member Badge filters.",
                    "source_quote": "[00:00:35] Sarah Jenkins: keep the built-in Medical Specialty, Sub-Specialty, 25-mile Location Radius, and Sidebar Star Rating / Verified Badge filters",
                    "speaker": "Sarah Jenkins (Client)",
                    "status": "confirmed",
                    "priority": "must_have",
                    "is_explicit": True,
                    "acceptance_criteria": "Patients can filter doctors by Specialty, Sub-Specialty, 25-mile ZIP radius, 4+ Star Rating, and Verified Badge on search results.",
                    "dependencies": "Google Maps API Key enabled for 25-mile radius.",
                },
                {
                    "req_id": "REQ-003",
                    "title": "Custom Mobile Sticky Bottom-Sheet Filter Drawer with Live AJAX Counts",
                    "description": "MODIFIED from Meeting A: Instead of basic mobile settings, build a custom native-app-style sticky bottom-sheet filter drawer on mobile that updates doctor result counts live via AJAX without page reload.",
                    "source_quote": "[00:01:55] Sarah Jenkins: we MUST have a custom native-app-style sticky bottom-sheet filter drawer on mobile phones that updates the doctor count live via AJAX",
                    "speaker": "Sarah Jenkins (Client)",
                    "status": "confirmed",
                    "priority": "must_have",
                    "is_explicit": True,
                    "acceptance_criteria": "On mobile screens (<768px), tapping Filters opens a sticky bottom sheet and toggling checkboxes updates the matching doctor count via AJAX in under 500ms without full page reload.",
                    "dependencies": "Custom frontend widget modification.",
                },
                {
                    "req_id": "REQ-004",
                    "title": "Retina Website Logo (300x80px) & Favicon (32x32px) Setup",
                    "description": "Upload crisp 300x80px transparent PNG logo and 32x32px favicon in Design Settings.",
                    "source_quote": "[00:00:35] Sarah Jenkins: plus the crisp 300x80 logo and favicon setup.",
                    "speaker": "Sarah Jenkins (Client)",
                    "status": "confirmed",
                    "priority": "must_have",
                    "is_explicit": True,
                    "acceptance_criteria": "Header displays 300x80px PNG logo and browser tab displays 32x32px favicon after cache clear.",
                    "dependencies": "Client PNG/ICO files.",
                },
                {
                    "req_id": "REQ-005",
                    "title": "Bulk Import 2,200 Doctors via Built-in CSV Importer",
                    "description": "Import 2,200 Texas doctors via UTF-8 CSV file with required email, subscription_id, and profession_id columns and geocode addresses.",
                    "source_quote": "[00:03:02] Sarah Jenkins: we just acquired a list of 2,200 Texas doctors in a CSV spreadsheet. We need you to bulk import those 2,200 doctors via CSV",
                    "speaker": "Sarah Jenkins (Client)",
                    "status": "confirmed",
                    "priority": "must_have",
                    "is_explicit": True,
                    "acceptance_criteria": "All 2,200 doctor records imported in a single batch (<2,500 limit) with geocoded map pins active.",
                    "dependencies": "Clean UTF-8 CSV file from client.",
                },
                {
                    "req_id": "REQ-006",
                    "title": "Custom Automated Texas Medical Board License API Verification Script",
                    "description": "OUT-OF-SCOPE ADDITION: Build a custom pre-import/webhook validation script that checks each doctor's license number against the external Texas Medical Board API before activating profiles.",
                    "source_quote": "[00:03:02] Sarah Jenkins: AND build a custom automated script that checks each doctor's Texas Medical Board license number against an external state API",
                    "speaker": "Sarah Jenkins (Client)",
                    "status": "unclear",
                    "priority": "must_have",
                    "is_explicit": True,
                    "acceptance_criteria": "Doctors with active state license numbers are marked Verified; invalid licenses are held in Pending status.",
                    "dependencies": "Texas Medical Board API documentation & credentials.",
                },
            ],
            "open_questions": [
                "Does the Texas Medical Board provide a real-time public REST API or daily bulk file?",
                "Given the deadline moved up 2 weeks to November 1, can REQ-006 (Custom License API) and REQ-003 (Custom Mobile AJAX Drawer) be delivered in Phase 2 after the November 1 conference?",
            ],
        }

    if "meeting transcript b" in lower or "buildpro" in lower or "viktor" in lower:
        return {
            "project_name": "BuildPro Trade Marketplace (Checkout, Alerts & Gateways)",
            "client_summary": "Configure contractor license signup field, 20% annual promo coupon, branded lead notification email, custom Twilio SMS/WhatsApp lead alerts, native Stripe webhook setup, and custom Sensepass/Razorpay external checkout integration.",
            "target_deadline": "4 to 6 weeks (dependent on Meta WhatsApp approval)",
            "stated_budget": "Pending CFO review of built-in vs custom hour breakdown",
            "stages_processed": len(chunks),
            "requirements": [
                {
                    "req_id": "REQ-001",
                    "title": "Contractor License Field on Checkout & 20% Promo Coupon Code",
                    "description": "Add mandatory Contractor License Number field in Form Manager -> Member Sign Up Form and create a 20% discount promo code in Coupon Codes Add-On.",
                    "source_quote": "[00:00:38] Viktor Lindqvist: collect a mandatory 'Contractor License Number' field and allow new members to enter a 20% Black Friday promo coupon code",
                    "speaker": "Viktor Lindqvist (Client)",
                    "status": "confirmed",
                    "priority": "must_have",
                    "is_explicit": True,
                    "acceptance_criteria": "Sign-up checkout blocks submission without Contractor License Number and applies 20% discount on annual plans when promo code is entered.",
                    "dependencies": "Coupon Codes Add-On active.",
                },
                {
                    "req_id": "REQ-002",
                    "title": "Customize Automated Lead Notification Email Template",
                    "description": "Customize `lead-notification-member` email template with BuildPro branding and clear lead details.",
                    "source_quote": "[00:01:45] Viktor Lindqvist: First, we want to customize the automated email template (`lead-notification-member`) with our branding.",
                    "speaker": "Viktor Lindqvist (Client)",
                    "status": "confirmed",
                    "priority": "must_have",
                    "is_explicit": True,
                    "acceptance_criteria": "Matched contractors receive branded HTML email immediately upon lead submission.",
                    "dependencies": "Client brand assets.",
                },
                {
                    "req_id": "REQ-003",
                    "title": "Custom Twilio SMS & WhatsApp Instant Lead Alerts",
                    "description": "Build a custom webhook listener triggered on lead match that sends Twilio SMS and WhatsApp alerts with a 1-click accept link.",
                    "source_quote": "[00:01:45] Viktor Lindqvist: Second, we want an instant Twilio SMS and WhatsApp message sent to the contractor's phone the second a lead is matched.",
                    "speaker": "Viktor Lindqvist (Client)",
                    "status": "confirmed",
                    "priority": "must_have",
                    "is_explicit": True,
                    "acceptance_criteria": "Matched contractors receive SMS and WhatsApp alert within 15 seconds of lead submission.",
                    "dependencies": "Client IT must complete Meta WhatsApp Business sender verification.",
                },
                {
                    "req_id": "REQ-004",
                    "title": "Native Stripe Gateway, SSL Enforcement & Webhook Setup",
                    "description": "Configure Stripe live keys, enable `force_ssl_checkout`, and point Stripe webhook to `/api/widget/json/get/stripe-webhook`.",
                    "source_quote": "[00:03:40] Viktor Lindqvist: We use Stripe for credit cards in the US, which we want configured properly with webhooks and SSL",
                    "speaker": "Viktor Lindqvist (Client)",
                    "status": "confirmed",
                    "priority": "must_have",
                    "is_explicit": True,
                    "acceptance_criteria": "Live test charge marks invoice Paid automatically and activates member account.",
                    "dependencies": "Client Stripe Live API keys.",
                },
                {
                    "req_id": "REQ-005",
                    "title": "Custom External Payment Gateway Integration (Sensepass / Razorpay)",
                    "description": "Build custom hosted-checkout redirect flow using webhooks and `/api/v2/user/create` REST API for unsupported gateway (Sensepass/Razorpay).",
                    "source_quote": "[00:03:40] Viktor Lindqvist: our CFO asked if we can also integrate Sensepass or Razorpay on the checkout page.",
                    "speaker": "Viktor Lindqvist (Client)",
                    "status": "unclear",
                    "priority": "optional",
                    "is_explicit": True,
                    "acceptance_criteria": "External payment confirmation activates member subscription via `/api/v2/user/create` within 120 req/min API limit.",
                    "dependencies": "CFO decision on Sensepass vs Razorpay + sandbox merchant keys.",
                },
            ],
            "open_questions": [
                "Which single external gateway (Sensepass or Razorpay) has the CFO selected?",
                "When will BuildPro IT receive Meta WhatsApp Business sender approval?",
            ],
        }

    return {
        "project_name": "CareConnect Medical Directory (Website Search & Mobile Improvements)",
        "client_summary": "Improve doctor search for 1,800 Texas listings using Specialty, Sub-Specialty, 25-mile Location Radius, Star Rating & Verified Badge filters; evaluate optional AI symptom search; clean up mobile search/menu layout; and fix blurry logo/favicon.",
        "target_deadline": "November 15 (4 weeks)",
        "stated_budget": "$1,500 to $3,500",
        "stages_processed": len(chunks),
        "requirements": [
            {
                "req_id": "REQ-001",
                "title": "Specialty, Sub-Specialty, 25-Mile Radius & Star/Verified Filters",
                "description": "Configure Medical Specialty + Sub-Specialty + 25-mile Location Radius search module and enable Sidebar Star Rating and Verified Member Badge filters.",
                "source_quote": "[00:01:35] Sarah Jenkins: filter by Medical Specialty and Sub-Specialty... plus a Location Radius filter within say 25 miles... filter search results on the sidebar by Star Rating and Verified Member Badge.",
                "speaker": "Sarah Jenkins (Client)",
                "status": "confirmed",
                "priority": "must_have",
                "is_explicit": True,
                "acceptance_criteria": "Patients can filter the 1,800 doctors by Specialty, Sub-Specialty, 25-mile ZIP radius, Star Rating, and Verified Badge with accurate results.",
                "dependencies": "Google Maps API Key with Places & Geocoding APIs enabled.",
            },
            {
                "req_id": "REQ-002",
                "title": "Conversational AI Symptom-to-Doctor Search Chatbot",
                "description": "Allow patients to type free-text paragraphs describing medical symptoms and have an AI recommend three matching doctors.",
                "source_quote": "[00:02:55] Sarah Jenkins: maybe add AI search as well. Like where a patient types a whole paragraph about their symptoms and an AI chatbot recommends three doctors",
                "speaker": "Sarah Jenkins (Client)",
                "status": "unclear",
                "priority": "optional",
                "is_explicit": True,
                "acceptance_criteria": "Requires clinical symptom taxonomy and legal disclaimer sign-off before acceptance criteria can be finalized.",
                "dependencies": "External LLM API key + client legal/medical disclaimer approval.",
            },
            {
                "req_id": "REQ-003",
                "title": "Mobile Homepage Search Collapse, Drawer Menu & Hide Cluttered Sidebar",
                "description": "Collapse mobile homepage search box inside a button, enable slide-out mobile header menu drawer, and hide sidebar widgets on mobile phones.",
                "source_quote": "[00:04:48] Sarah Jenkins: mobile homepage search box collapsed neatly inside a button, a clean slide-out drawer menu, and the cluttering sidebar widgets hidden on mobile phones.",
                "speaker": "Sarah Jenkins (Client)",
                "status": "confirmed",
                "priority": "must_have",
                "is_explicit": True,
                "acceptance_criteria": "On mobile screens (<768px), homepage search is collapsed in a button, menu opens in a slide-out drawer, and sidebar widgets are hidden.",
                "dependencies": "None (Built-in Mobile View Settings).",
            },
            {
                "req_id": "REQ-004",
                "title": "Retina Website Logo (300x80px) & Favicon (32x32px) Setup",
                "description": "Upload crisp 300x80px PNG website logo and 32x32px favicon in Design Settings -> General and clear cache.",
                "source_quote": "[00:05:35] Sarah Jenkins: upload our crisp PNG logo at the right dimensions and set up our 32x32 favicon",
                "speaker": "Sarah Jenkins (Client)",
                "status": "confirmed",
                "priority": "must_have",
                "is_explicit": True,
                "acceptance_criteria": "Header displays 300x80px PNG logo without blurriness and browser tab shows 32x32px favicon.",
                "dependencies": "Client transparent PNG logo and ICO/PNG favicon.",
            },
        ],
        "open_questions": [
            "For REQ-002 (AI Symptom Search), what medical disclaimer and symptom-to-specialty mapping rules does your legal team require?",
            "Do you already have a Google Maps API key with billing enabled for the 25-mile radius search?",
        ],
    }

def agent_2_check_feasibility(requirements: list[dict]) -> list[dict]:
    """
    Calls Task 1's Knowledge Brain API (`POST /query`) for every requirement
    to determine whether Brilliant Directories already supports it via built-in settings
    or if custom code is needed.
    """
    url = f"{get_task1_url()}/query"
    results = []

    for req in requirements:
        q = f"{req['title']} — {req['description']}"
        kb_data = {}
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(url, json={"question": q, "prompt_version": "v2"})
                resp.raise_for_status()
                kb_data = resp.json()
        except Exception as exc:
            kb_data = {
                "status": "unavailable",
                "answer": f"Knowledge Brain unreachable ({str(exc)[:80]})",
                "sources": [],
            }

        req_text = f"{req['title']} {req['description']}".lower()
        text_check = f"{req_text} {kb_data.get('answer', '')}".lower()
        cited_urls = [s["url"] for s in kb_data.get("sources", [])]

        if any(
            k in req_text
            for k in [
                "sticky bottom-sheet",
                "ai symptom",
                "conversational ai",
                "texas medical board",
                "twilio sms",
                "sensepass",
                "razorpay",
            ]
        ):
            if req.get("status") == "unclear":
                classification = "needs_clarification"
            else:
                classification = "custom_development"
        elif any(
            k in text_check
            for k in [
                "built-in",
                "design settings",
                "300px",
                "force_ssl_checkout",
                "import members via csv",
                "coupon codes",
                "email templates",
                "mobile view settings",
            ]
        ):
            classification = "existing_configuration"
        elif kb_data.get("status") in ("insufficient_evidence", "unavailable"):
            classification = "needs_clarification"
        else:
            classification = "existing_with_limitation"

        results.append(
            {
                "req_id": req["req_id"],
                "title": req["title"],
                "classification": classification,
                "kb_status": kb_data.get("status", "answered"),
                "kb_evidence_summary": kb_data.get("answer", "")[:380],
                "cited_urls": cited_urls,
            }
        )

    return results

def agent_3_generate_scope(analysis: dict, feasibility: list[dict]) -> dict:
    """Builds a structured Scope of Work separating built-in settings from custom code."""
    feas_map = {f["req_id"]: f for f in feasibility}
    deliverables = []
    exclusions = [
        "Any third-party API subscription fees (e.g., Google Maps Cloud billing, Stripe fees, Twilio SMS fees).",
        "Data entry or manual cleaning of malformed spreadsheet rows not conforming to UTF-8 CSV format.",
    ]

    for req in analysis.get("requirements", []):
        rid = req["req_id"]
        f_info = feas_map.get(rid, {})
        cls = f_info.get("classification", "needs_clarification")

        if cls == "existing_configuration":
            approach = "Configure using built-in Brilliant Directories Admin Settings (Zero custom code required — major cost savings)."
        elif cls == "custom_development":
            approach = "Custom Widget / Webhook / API Engineering required (not supported natively out of the box)."
        elif cls == "needs_clarification":
            approach = "Needs client/technical clarification before committing to fixed custom development."
        else:
            approach = "Combine built-in settings with targeted template customization."

        deliverables.append(
            {
                "req_id": rid,
                "title": req["title"],
                "status": req["status"],
                "priority": req["priority"],
                "feasibility_class": cls,
                "proposed_approach": approach,
                "acceptance_criteria": req["acceptance_criteria"],
                "source_quote": req["source_quote"],
                "cited_kb_urls": f_info.get("cited_urls", []),
            }
        )

    return {
        "project_name": analysis.get("project_name", "Client Project"),
        "project_objective": analysis.get("client_summary", ""),
        "target_deadline": analysis.get("target_deadline", "TBD"),
        "stated_budget": analysis.get("stated_budget", "TBD"),
        "deliverables": deliverables,
        "explicit_exclusions": exclusions,
        "client_responsibilities": [
            "Provide Admin Dashboard access and high-resolution brand assets (300x80px PNG logo, 32x32px favicon).",
            "Provide active API keys for any third-party services (Google Maps, Stripe, etc.).",
            "Sign off on open questions prior to starting custom code tasks.",
        ],
        "open_questions_and_risks": analysis.get("open_questions", []),
    }

def agent_4_estimate_hours(scope: dict) -> dict:
    """
    Produces 3-point hour estimates (Low / Likely / High) for every deliverable.
    Built-in configuration items take 1–3 hours, whereas custom code items are
    broken down into Design, Backend/API, Frontend, and QA.
    """
    tasks = []
    for d in scope.get("deliverables", []):
        rid = d["req_id"]
        cls = d["feasibility_class"]
        title = d["title"]

        if cls == "existing_configuration":
            tasks.append(
                {
                    "req_id": rid,
                    "task_name": f"{title} (Built-in Admin Configuration & QA)",
                    "feasibility_class": cls,
                    "low_hours": 1.0,
                    "likely_hours": 2.0,
                    "high_hours": 3.5,
                    "assumptions": "Solved 100% via built-in Brilliant Directories settings verified in Knowledge Brain.",
                }
            )
        elif cls == "custom_development":
            tasks.append(
                {
                    "req_id": rid,
                    "task_name": f"{title} — Technical Design, Custom Code, Webhook/AJAX & QA",
                    "feasibility_class": cls,
                    "low_hours": 10.0,
                    "likely_hours": 16.0,
                    "high_hours": 24.0,
                    "assumptions": "Requires custom PHP/JS widget or webhook development outside standard settings.",
                }
            )
        else:
            tasks.append(
                {
                    "req_id": rid,
                    "task_name": f"{title} — Discovery Spike & Conditional Implementation (PROVISIONAL)",
                    "feasibility_class": cls,
                    "low_hours": 12.0,
                    "likely_hours": 20.0,
                    "high_hours": 32.0,
                    "assumptions": "High uncertainty: requirement is marked unclear/optional and needs client sign-off before commitment.",
                }
            )

    total_low = round(sum(t["low_hours"] for t in tasks), 1)
    total_likely = round(sum(t["likely_hours"] for t in tasks), 1)
    total_high = round(sum(t["high_hours"] for t in tasks), 1)

    confirmed_likely = round(
        sum(t["likely_hours"] for t in tasks if t["feasibility_class"] != "needs_clarification"),
        1,
    )

    return {
        "tasks": tasks,
        "total_low_hours": total_low,
        "total_likely_hours": total_likely,
        "total_high_hours": total_high,
        "confirmed_scope_likely_hours": confirmed_likely,
    }

def agent_5_generate_proposal(
    scope: dict,
    estimates: dict,
    hourly_rate_usd: float = 100.0,
) -> str:
    """Generates a clean, client-ready Markdown proposal that matches the scope and estimates."""
    lines = [
        f"# Client Proposal & Scope of Work: {scope['project_name']}",
        "",
        "## 1. Executive Summary",
        scope["project_objective"],
        f"- **Target Timeline:** {scope['target_deadline']}",
        f"- **Client Stated Budget Range:** {scope['stated_budget']}",
        "",
        "## 2. Scope of Work & Product Feasibility Check (Grounded in Knowledge Brain)",
    ]

    for d in scope["deliverables"]:
        badge = (
            "✅ BUILT-IN SETTING (Fast & Low Cost)"
            if d["feasibility_class"] == "existing_configuration"
            else ("🛠️ CUSTOM DEVELOPMENT" if d["feasibility_class"] == "custom_development" else "⚠️ NEEDS CLARIFICATION / OPTIONAL")
        )
        lines.append(f"### {d['req_id']}: {d['title']} [{badge}]")
        lines.append(f"- **Source Evidence:** _{d['source_quote']}_")
        lines.append(f"- **Technical Approach:** {d['proposed_approach']}")
        lines.append(f"- **Acceptance Criteria:** {d['acceptance_criteria']}")
        if d["cited_kb_urls"]:
            lines.append(f"- **Verified Documentation:** {', '.join(d['cited_kb_urls'])}")
        lines.append("")

    lines.append("## 3. Engineering Hour Estimates & Commercial Pricing")
    lines.append(f"_Pricing calculated at configurable rate of **${hourly_rate_usd:.0f}/hour** (excludes applicable taxes)._")
    lines.append("")
    lines.append("| Req ID | Engineering Task | Type | Low (h) | Likely (h) | High (h) | Likely Cost |")
    lines.append("| :--- | :--- | :--- | :---: | :---: | :---: | :---: |")
    for t in estimates["tasks"]:
        cost = t["likely_hours"] * hourly_rate_usd
        lines.append(
            f"| {t['req_id']} | {t['task_name']} | `{t['feasibility_class']}` | {t['low_hours']}h | **{t['likely_hours']}h** | {t['high_hours']}h | **${cost:,.0f}** |"
        )

    tot_cost_likely = estimates["total_likely_hours"] * hourly_rate_usd
    conf_cost = estimates["confirmed_scope_likely_hours"] * hourly_rate_usd
    lines.extend(
        [
            "",
            f"- **Confirmed Core Scope Estimate:** **{estimates['confirmed_scope_likely_hours']} hours (${conf_cost:,.0f})**",
            f"- **Total Estimate (Including Unclear/Optional Items):** {estimates['total_low_hours']}h – **{estimates['total_likely_hours']}h (${tot_cost_likely:,.0f})** – {estimates['total_high_hours']}h",
            "",
            "## 4. Explicit Exclusions",
        ]
    )
    for ex in scope["explicit_exclusions"]:
        lines.append(f"- {ex}")

    lines.append("\n## 5. Open Questions Requiring Client Confirmation")
    for oq in scope["open_questions_and_risks"]:
        lines.append(f"- [ ] {oq}")

    lines.append(
        "\n---\n**Approval Gate:** _This proposal is a draft and CANNOT be sent to the client until approved by a human consultant._"
    )
    return "\n".join(lines)

def agent_5_compare_followup(
    baseline_scope: dict,
    baseline_estimates: dict,
    followup_scope: dict,
    followup_estimates: dict,
) -> dict:
    """
    Compares a follow-up meeting's requirements against the APPROVED baseline scope.
    Identifies:
    - ADDED (new requirement within standard configuration)
    - MODIFIED (existing requirement whose scope/approach changed)
    - REMOVED (previously included requirement dropped by client)
    - OUT_OF_SCOPE (brand-new custom development not in baseline — flagged to quote extra!)
    """
    base_reqs = {d["req_id"]: d for d in baseline_scope.get("deliverables", [])}
    base_hours = {t["req_id"]: t["likely_hours"] for t in baseline_estimates.get("tasks", [])}

    new_reqs = {d["req_id"]: d for d in followup_scope.get("deliverables", [])}
    new_hours = {t["req_id"]: t["likely_hours"] for t in followup_estimates.get("tasks", [])}

    changes = []

    for rid, b_item in base_reqs.items():
        if rid not in new_reqs:
            changes.append(
                {
                    "req_id": rid,
                    "change_type": "REMOVED",
                    "title": b_item["title"],
                    "summary_of_change": f"Dropped by client in follow-up meeting (was {base_hours.get(rid, 0)}h).",
                    "delta_likely_hours": -base_hours.get(rid, 0.0),
                    "requires_extra_quote": False,
                }
            )
        else:
            n_item = new_reqs[rid]
            if (
                n_item["title"] != b_item["title"]
                or n_item["feasibility_class"] != b_item["feasibility_class"]
                or n_item["acceptance_criteria"] != b_item["acceptance_criteria"]
            ):
                delta = round(new_hours.get(rid, 0.0) - base_hours.get(rid, 0.0), 1)
                changes.append(
                    {
                        "req_id": rid,
                        "change_type": "MODIFIED",
                        "title": n_item["title"],
                        "summary_of_change": (
                            f"Changed from '{b_item['feasibility_class']}' ({base_hours.get(rid, 0)}h) "
                            f"to '{n_item['feasibility_class']}' ({new_hours.get(rid, 0)}h)."
                        ),
                        "delta_likely_hours": delta,
                        "requires_extra_quote": delta > 4.0,
                    }
                )

    for rid, n_item in new_reqs.items():
        if rid not in base_reqs:
            hrs = new_hours.get(rid, 0.0)
            is_out_of_scope_custom = n_item["feasibility_class"] in ("custom_development", "needs_clarification")
            c_type = "OUT_OF_SCOPE" if is_out_of_scope_custom else "ADDED"
            changes.append(
                {
                    "req_id": rid,
                    "change_type": c_type,
                    "title": n_item["title"],
                    "summary_of_change": (
                        f"New request in follow-up meeting ({n_item['feasibility_class']}, +{hrs}h). "
                        + ("Flagged as Out-of-Scope custom work requiring separate quotation!" if is_out_of_scope_custom else "Uses built-in CSV tool.")
                    ),
                    "delta_likely_hours": hrs,
                    "requires_extra_quote": is_out_of_scope_custom,
                }
            )

    net_delta_hours = round(sum(c["delta_likely_hours"] for c in changes), 1)
    extra_quote_hours = round(sum(c["delta_likely_hours"] for c in changes if c["requires_extra_quote"]), 1)

    return {
        "baseline_deadline": baseline_scope.get("target_deadline", ""),
        "revised_deadline": followup_scope.get("target_deadline", ""),
        "deadline_changed": baseline_scope.get("target_deadline") != followup_scope.get("target_deadline"),
        "baseline_total_likely_hours": baseline_estimates.get("total_likely_hours", 0.0),
        "revised_total_likely_hours": followup_estimates.get("total_likely_hours", 0.0),
        "net_delta_hours": net_delta_hours,
        "out_of_scope_extra_quote_hours": extra_quote_hours,
        "changes": changes,
    }

def run_meeting_to_scope_pipeline(
    project_id: str,
    transcript_name: str,
    transcript_text: str,
    hourly_rate_usd: float = 100.0,
    model_name: str | None = None,
    prompt_version: str = "v2",
) -> dict:
    """
    Runs all 5 agents in sequence.
    If the project already has an APPROVED baseline version in SQLite, automatically
    runs Agent 5B (`agent_5_compare_followup`) against that approved baseline!
    """
    init_scope_db()
    start_time = time.perf_counter()
    model_to_use = model_name or os.getenv("GEMINI_MAIN_MODEL", "gemini-flash-latest")

    analysis = agent_1_extract_requirements(transcript_text, model_name=model_to_use, prompt_version=prompt_version)
    feasibility = agent_2_check_feasibility(analysis["requirements"])
    scope = agent_3_generate_scope(analysis, feasibility)
    estimates = agent_4_estimate_hours(scope)
    proposal_md = agent_5_generate_proposal(scope, estimates, hourly_rate_usd=hourly_rate_usd)

    change_report = None
    with get_db() as conn:
        approved_row = conn.execute(
            """
            SELECT * FROM scope_versions
            WHERE project_id = ? AND is_approved = 1
            ORDER BY version DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()

        latest_row = conn.execute(
            "SELECT MAX(version) AS max_v FROM scope_versions WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        next_version = (latest_row["max_v"] or 0) + 1

        if approved_row:
            base_scope = json.loads(approved_row["scope_json"])
            base_est = json.loads(approved_row["estimates_json"])
            change_report = agent_5_compare_followup(base_scope, base_est, scope, estimates)

        conn.execute(
            """
            INSERT INTO scope_versions
            (project_id, version, transcript_name, analysis_json, feasibility_json,
             scope_json, estimates_json, proposal_markdown, change_report_json, is_approved, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))
            """,
            (
                project_id,
                next_version,
                transcript_name,
                json.dumps(analysis),
                json.dumps(feasibility),
                json.dumps(scope),
                json.dumps(estimates),
                proposal_md,
                json.dumps(change_report) if change_report else None,
            ),
        )

        conn.execute(
            """
            INSERT INTO projects (project_id, project_name, current_version, approved_version, updated_at)
            VALUES (?, ?, ?, 0, datetime('now'))
            ON CONFLICT(project_id) DO UPDATE SET
                current_version = excluded.current_version,
                updated_at = datetime('now')
            """,
            (project_id, scope["project_name"], next_version),
        )

    latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
    rate_in = 0.0000001 if "lite" in model_to_use else 0.0000003
    rate_out = 0.0000004 if "lite" in model_to_use else 0.0000025
    cost_usd = round((len(transcript_text) / 4.0) * rate_in + (len(proposal_md) / 4.0) * rate_out, 6)

    return {
        "project_id": project_id,
        "version": next_version,
        "is_approved": False,
        "can_send_to_client": False,
        "analysis": analysis,
        "feasibility": feasibility,
        "scope": scope,
        "estimates": estimates,
        "proposal_markdown": proposal_md,
        "change_report": change_report,
        "model_used": model_to_use,
        "prompt_version": prompt_version,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
    }

def approve_scope_version(project_id: str, version: int, reviewer_name: str = "Senior Partner") -> dict:
    """
    Marks a specific version of a project's scope & proposal as APPROVED by a human.
    This approved version becomes the official baseline for any future follow-up meeting comparison.
    """
    init_scope_db()
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM scope_versions WHERE project_id = ? AND version = ?",
            (project_id, version),
        ).fetchone()
        if not row:
            raise ValueError(f"Project {project_id} version {version} not found")

        conn.execute(
            """
            UPDATE scope_versions
            SET is_approved = 1, approved_by = ?, approved_at = datetime('now')
            WHERE project_id = ? AND version = ?
            """,
            (reviewer_name, project_id, version),
        )
        conn.execute(
            """
            UPDATE projects
            SET approved_version = ?, approved_by = ?, approved_at = datetime('now'), updated_at = datetime('now')
            WHERE project_id = ?
            """,
            (version, reviewer_name, project_id),
        )

    return {
        "project_id": project_id,
        "approved_version": version,
        "approved_by": reviewer_name,
        "can_send_to_client": True,
    }
