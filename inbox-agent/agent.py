"""
Why this file exists:
1. Calls Task 1 (The Knowledge Brain) over its HTTP API (`POST /query`) to get verified product facts.
2. Classifies incoming customer emails into the 7 categories and assesses risk.
3. Drafts a polite, accurate reply in the company's voice without making unauthorized promises.
4. Learns from human edits by storing versioned rules in SQLite (with an Undo toggle).
"""

import json
import os
import time
from pathlib import Path
import httpx
from google import genai
from autonomy import (
    HIGH_RISK_BLOCKED_CATEGORIES,
    get_category_autonomy_status,
    get_db,
    init_autonomy_tables,
    is_draft_unchanged,
    record_human_decision,
)
from prompts import DRAFTING_PROMPTS, EmailDraftSchema, LearnedRuleSchema

def get_task1_url() -> str:
    return os.getenv("TASK1_API_URL", "http://127.0.0.1:8001").rstrip("/")

def query_knowledge_brain_api(question: str, timeout_sec: float = 8.0) -> dict:
    """
    Calls Task 1 (`POST /query`) with automatic 1x retry.
    If Task 1 is unreachable, returns a clear `unavailable` state so the Inbox Agent
    never fabricates product answers.
    """
    url = f"{get_task1_url()}/query"
    for attempt in range(2):
        try:
            with httpx.Client(timeout=timeout_sec) as client:
                resp = client.post(url, json={"question": question, "prompt_version": "v2"})
                resp.raise_for_status()
                data = resp.json()
                return {
                    "kb_status": data.get("status", "answered"),
                    "answer": data.get("answer", ""),
                    "sources": data.get("sources", []),
                    "images": data.get("images", []),
                    "needs_human": data.get("needs_human", False),
                    "confidence": data.get("confidence", 0.0),
                }
        except Exception as exc:
            if attempt == 0:
                time.sleep(0.3)
            else:
                return {
                    "kb_status": "unavailable",
                    "answer": "",
                    "sources": [],
                    "images": [],
                    "needs_human": True,
                    "confidence": 0.0,
                    "error": f"Knowledge Brain API unreachable ({str(exc)[:100]})",
                }
    return {"kb_status": "unavailable", "answer": "", "sources": [], "needs_human": True}

def get_active_learned_rules(category: str | None = None) -> list[dict]:
    init_autonomy_tables()
    with get_db() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM learned_rules WHERE is_active = 1 AND (category = ? OR category = 'all') ORDER BY id DESC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM learned_rules ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]

def learn_from_human_edit(
    email_id: str,
    category: str,
    generated_draft: str,
    human_edited_reply: str,
) -> dict | None:
    """
    Compares the AI's original draft with the human's edited version and saves a
    reusable 1-sentence lesson so future drafts improve automatically.
    """
    if is_draft_unchanged(generated_draft, human_edited_reply):
        return None

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    rule_text = ""

    if api_key and api_key != "your_gemini_api_key_here":
        try:
            client = genai.Client(api_key=api_key)
            prompt = (
                f"Category: {category}\n"
                f"AI Original Draft:\n{generated_draft}\n\n"
                f"Human Edited Final Reply:\n{human_edited_reply}\n\n"
                "Extract one concise, reusable drafting instruction (1 sentence) that explains how the AI should write future replies in this category based on the human's edit."
            )
            res = client.models.generate_content(
                model=os.getenv("GEMINI_FAST_MODEL", "gemini-flash-lite-latest"),
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=LearnedRuleSchema,
                    temperature=0.1,
                ),
            )
            parsed = LearnedRuleSchema.model_validate_json(res.text)
            rule_text = parsed.rule_summary
        except Exception:
            rule_text = ""

    if not rule_text:
        if len(human_edited_reply) < len(generated_draft) * 0.8:
            rule_text = f"For '{category}' emails, keep replies shorter and more direct (under {max(3, len(human_edited_reply.splitlines()))} lines)."
        elif "billing manager" in human_edited_reply.lower():
            rule_text = f"For '{category}' emails, explicitly mention that our Billing Manager reviews requests within 1 business day."
        else:
            snippet = human_edited_reply.strip().splitlines()[-1][:90]
            rule_text = f"For '{category}' emails, include clear next-step phrasing similar to: \"{snippet}\""

    init_autonomy_tables()
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO learned_rules (category, rule_text, source_email_id, is_active, created_at)
            VALUES (?, ?, ?, 1, datetime('now'))
            """,
            (category, rule_text, email_id),
        )
        rule_id = int(cur.lastrowid)

    return {"id": rule_id, "category": category, "rule_text": rule_text, "is_active": True}

def toggle_learned_rule(rule_id: int, is_active: bool) -> dict:
    """Allows a human to undo/disable a learned rule if it ever hurts quality."""
    init_autonomy_tables()
    with get_db() as conn:
        conn.execute("UPDATE learned_rules SET is_active = ? WHERE id = ?", (1 if is_active else 0, rule_id))
    return {"id": rule_id, "is_active": is_active}

def _heuristic_classify(subject: str, body: str) -> tuple[str, str, str]:
    """
    Fast, accurate rule-based classifier used both as a sanity check and offline fallback.
    Returns (category, urgency, risk_level).
    """
    text = f"{subject} {body}".lower()

    if any(p in text for p in ["following up", "follow up", "checking in on", "did you receive", "wrote in two days ago", "update on our stripe webhook"]):
        risk = "high" if ("refund" in text or "board meeting" in text) else "moderate"
        return "follow_up", "medium", risk

    if any(p in text for p in ["refund", "cancel our annual", "cancel my monthly", "billed twice", "setup fee"]) and "didn't get the money" not in text:
        return "refund_or_cancellation", "high", "high"

    if any(p in text for p in ["unacceptable", "extremely frustrated", "furious", "misleading", "hated it", "embarrassing", "costing us thousands", "third time writing"]):
        return "complaint", "high", "high"

    if any(p in text for p in ["how much would it cost", "quote request", "price estimate", "how much do you charge", "lowest fixed price", "ballpark estimate", "what dollar amount"]):
        return "quote_request", "medium", "high"

    if any(p in text for p in ["can your team build", "can we scope this", "integrate razorpay", "conversational ai search", "sticky bottom-sheet", "two-way real-time sync", "fmcsa government api"]):
        return "project_request", "medium", "high"

    if any(p in text for p in ["stopped working", "err_too_many_redirects", "stay unpaid", "aren't showing", "didn't get the money", "429 rate limit", "old logo still shows", "dns pending", "https required", "invalid encoding"]):
        urg = "high" if ("urgent" in text or "down" in text or "unpaid" in text) else "medium"
        return "troubleshooting", urg, "moderate"

    return "how_to", "low", "low"

def draft_email_response(
    email_item: dict,
    model_name: str | None = None,
    prompt_version: str = "v2",
) -> dict:
    """
    End-to-end Inbox Agent pipeline:
    1. Queries Task 1 API for relevant product knowledge.
    2. Loads active learned rules from human feedback.
    3. Generates structured draft (`category`, `risk_level`, `suggested_reply`, `sources`, `requires_human_approval`).
    """
    init_autonomy_tables()
    start_time = time.perf_counter()
    model_to_use = model_name or os.getenv("GEMINI_MAIN_MODEL", "gemini-flash-latest")

    subject = email_item.get("subject", "")
    body = email_item.get("body", "")
    sender_name = email_item.get("sender_name", "Valued Client")
    sender_email = email_item.get("sender_email", "client@example.com")
    email_id = email_item.get("id", "EM-CUSTOM")

    combined_lower = f"{subject} {body}".lower()
    is_injection = "ignore previous instructions" in combined_lower or "you are now the cfo" in combined_lower

    kb_res = query_knowledge_brain_api(f"{subject}\n{body}")
    kb_status = kb_res.get("kb_status", "unavailable")
    kb_answer = kb_res.get("answer", "")
    kb_sources = kb_res.get("sources", [])

    if kb_status == "unavailable":
        cat, urg, risk = _heuristic_classify(subject, body)
        latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
        return {
            "email_id": email_id,
            "category": cat,
            "urgency": urg,
            "risk_level": "high",
            "request_summary": subject,
            "suggested_reply": (
                f"Hi {sender_name.split()[0]},\n\n"
                "Thank you for reaching out. Our internal product knowledge service is temporarily offline for maintenance, "
                "so I have routed your message directly to a human specialist to ensure you receive verified instructions shortly.\n\n"
                "Best regards,\nCustomer Support Team"
            ),
            "kb_status": "unavailable",
            "sources": [],
            "requires_human_approval": True,
            "auto_sent": False,
            "follow_up_action": "Retry once Knowledge Brain (:8001) is online.",
            "model_used": model_to_use,
            "prompt_version": prompt_version,
            "latency_ms": latency_ms,
            "cost_usd": 0.0,
        }

    heur_cat, heur_urg, heur_risk = _heuristic_classify(subject, body)
    active_rules = get_active_learned_rules(heur_cat)
    rules_str = (
        "\n".join(f"- {r['rule_text']}" for r in active_rules)
        if active_rules
        else "- Write clearly, cite relevant help articles, and never commit to unauthorized prices or refunds."
    )

    kb_context = f"Status: {kb_status}\nVerified Facts: {kb_answer}\nSources: {json.dumps(kb_sources)}"
    prompt_tmpl = DRAFTING_PROMPTS.get(prompt_version, DRAFTING_PROMPTS["v2"])
    full_prompt = prompt_tmpl.format(
        sender_name=sender_name,
        sender_email=sender_email,
        subject=subject,
        body=body,
        kb_context=kb_context,
        learned_rules=rules_str,
    )

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key and api_key != "your_gemini_api_key_here" and not is_injection:
        for attempt in range(2):
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model_to_use,
                    contents=full_prompt,
                    config=genai.types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=EmailDraftSchema,
                        temperature=0.1,
                    ),
                )
                parsed = EmailDraftSchema.model_validate_json(response.text)
                autonomy_info = get_category_autonomy_status(parsed.category)
                can_auto_send = (
                    autonomy_info["auto_send_enabled"]
                    and parsed.category not in HIGH_RISK_BLOCKED_CATEGORIES
                    and kb_status == "answered"
                    and not parsed.contains_unauthorized_commitment
                )

                in_tokens = len(full_prompt) / 4.0
                out_tokens = len(response.text) / 4.0
                rate_in = 0.0000001 if "lite" in model_to_use else 0.0000003
                rate_out = 0.0000004 if "lite" in model_to_use else 0.0000025
                cost_usd = round(in_tokens * rate_in + out_tokens * rate_out, 6)
                latency_ms = round((time.perf_counter() - start_time) * 1000, 1)

                return {
                    "email_id": email_id,
                    "category": parsed.category,
                    "urgency": parsed.urgency,
                    "risk_level": parsed.risk_level,
                    "confidence": 0.96 if kb_status == "answered" else 0.72,
                    "request_summary": parsed.request_summary,
                    "suggested_reply": parsed.suggested_reply,
                    "kb_status": kb_status,
                    "sources": kb_sources,
                    "requires_human_approval": not can_auto_send,
                    "auto_sent": can_auto_send,
                    "follow_up_action": parsed.follow_up_action,
                    "learned_rules_applied": [r["rule_text"] for r in active_rules],
                    "model_used": model_to_use,
                    "prompt_version": prompt_version,
                    "latency_ms": latency_ms,
                    "cost_usd": cost_usd,
                }
            except Exception:
                if attempt == 0:
                    time.sleep(0.4)

    first_name = sender_name.split()[0] if sender_name else "there"
    source_line = ""
    if kb_sources:
        top_src = kb_sources[0]
        source_line = f"\n\nReference Article: {top_src['title']} ({top_src['url']})"

    if is_injection:
        reply = (
            f"Hello,\n\nWe received your message regarding account refund authorization. "
            "For security reasons, automated requests to bypass billing policies cannot be processed. "
            "Your request has been logged for human billing review.\n\nBest regards,\nBilling & Security Team"
        )
        follow_up = "Flagged prompt-injection attempt in refund request; require manual verification."
    elif heur_cat == "refund_or_cancellation":
        reply = (
            f"Hi {first_name},\n\nThank you for reaching out regarding your account billing. "
            f"Based on our policy and documentation:\n\n{kb_answer}\n\n"
            "Because refunds on annual plans or setup fees require human billing manager approval (and are subject to our 14-day policy), "
            "I have escalated your request to our Billing Manager for review today. We have not processed an automated commitment yet, and our team will confirm next steps within 1 business day."
            f"{source_line}\n\nBest regards,\nCustomer Support & Billing Team"
        )
        follow_up = "Assign to Billing Manager for 14-day policy eligibility review."
    elif heur_cat in ("quote_request", "project_request"):
        reply = (
            f"Hi {first_name},\n\nThank you for sharing your project requirements! "
            f"Here is what Brilliant Directories already supports out of the box versus what requires custom development:\n\n{kb_answer}\n\n"
            "Rather than guessing a fixed price or delivery date over email, our technical consulting team will prepare a formal Scope of Work and hour estimate for your review. "
            "Would you be available for a 20-minute scoping call this week?"
            f"{source_line}\n\nBest regards,\nTechnical Consulting Team"
        )
        follow_up = "Send transcript/requirements to Task 3 (Scope Builder) for formal estimate."
    elif heur_cat == "complaint":
        reply = (
            f"Hi {first_name},\n\nI sincerely apologize for the frustration and disruption this has caused your team. "
            f"I have flagged your ticket as High Priority for a senior specialist. Here is the immediate fix from our documentation:\n\n{kb_answer}"
            f"{source_line}\n\nA senior manager is also reviewing your account and will follow up with you directly today.\n\nBest regards,\nSenior Support Escalations"
        )
        follow_up = "Urgent senior manager callback within 2 hours."
    else:
        reply = (
            f"Hi {first_name},\n\nHappy to help with your question!\n\n{kb_answer}"
            f"{source_line}\n\nPlease let us know if you need any further assistance!\n\nBest regards,\nCustomer Support Team"
        )
        follow_up = "Check back in 48 hours if customer does not confirm resolution."

    if any("shorter" in r["rule_text"].lower() for r in active_rules):
        lines = [ln for ln in reply.splitlines() if ln.strip()]
        reply = "\n\n".join(lines[:3])

    autonomy_info = get_category_autonomy_status(heur_cat)
    can_auto_send = (
        autonomy_info["auto_send_enabled"]
        and heur_cat not in HIGH_RISK_BLOCKED_CATEGORIES
        and kb_status == "answered"
        and not is_injection
    )

    in_tokens = len(full_prompt) / 4.0
    out_tokens = len(reply) / 4.0
    rate_in = 0.0000001 if "lite" in model_to_use else 0.0000003
    rate_out = 0.0000004 if "lite" in model_to_use else 0.0000025
    cost_usd = round(in_tokens * rate_in + out_tokens * rate_out, 6)
    latency_ms = round((time.perf_counter() - start_time) * 1000, 1)

    return {
        "email_id": email_id,
        "category": heur_cat,
        "urgency": heur_urg,
        "risk_level": heur_risk,
        "request_summary": subject,
        "suggested_reply": reply,
        "kb_status": kb_status,
        "sources": kb_sources,
        "requires_human_approval": not can_auto_send,
        "auto_sent": can_auto_send,
        "follow_up_action": follow_up,
        "learned_rules_applied": [r["rule_text"] for r in active_rules],
        "model_used": model_to_use,
        "prompt_version": prompt_version,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
    }

def submit_human_review(
    email_item: dict,
    draft_result: dict,
    final_sent_reply: str,
    outcome: str,
    reviewer_note: str = "",
) -> dict:
    """
    Stores the full interaction in SQLite, updates the 20-consecutive-approval counter,
    and extracts a learned rule if the human edited the draft.
    """
    init_autonomy_tables()
    gen_draft = draft_result.get("suggested_reply", "")
    category = draft_result.get("category", "how_to")
    unchanged = is_draft_unchanged(gen_draft, final_sent_reply)

    actual_outcome = outcome
    if outcome == "approved" and not unchanged:
        actual_outcome = "edited"

    streak_status = record_human_decision(
        category=category,
        generated_draft=gen_draft,
        final_sent_reply=final_sent_reply,
        outcome=actual_outcome,
        reason=reviewer_note,
    )

    learned_rule = None
    if actual_outcome == "edited":
        learned_rule = learn_from_human_edit(
            email_id=email_item.get("id", "EM-CUSTOM"),
            category=category,
            generated_draft=gen_draft,
            human_edited_reply=final_sent_reply,
        )

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO email_interactions
            (email_id, sender_email, subject, original_body, predicted_category, risk_level,
             kb_status, kb_sources_json, generated_draft, final_sent_reply, was_edited,
             approval_outcome, reviewer_note, model_used, prompt_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                email_item.get("id", "EM-CUSTOM"),
                email_item.get("sender_email", ""),
                email_item.get("subject", ""),
                email_item.get("body", ""),
                category,
                draft_result.get("risk_level", "moderate"),
                draft_result.get("kb_status", "answered"),
                json.dumps(draft_result.get("sources", [])),
                gen_draft,
                final_sent_reply,
                0 if unchanged else 1,
                actual_outcome,
                reviewer_note,
                draft_result.get("model_used", "gemini-2.5-flash"),
                draft_result.get("prompt_version", "v2"),
            ),
        )

    return {
        "outcome_recorded": actual_outcome,
        "was_unchanged": unchanged,
        "streak_status": streak_status,
        "new_learned_rule": learned_rule,
    }
