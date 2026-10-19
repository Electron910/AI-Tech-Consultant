"""
task3-meeting-to-scope/eval_task3.py
------------------------------------
Why this file exists:
Runs 20 evaluation cases on Task 3 (Meeting to Scope of Work) across
`gemini-2.5-flash-lite` and `gemini-2.5-flash`, measuring:
1. Requirement extraction & quote preservation (Meetings A, B, and C)
2. Product feasibility checks via Task 1 API (built-in settings vs custom code)
3. Plausible hour estimates (1-3h for built-in settings vs 10-24h for custom code)
4. Follow-up meeting change detection (ADDED, MODIFIED, REMOVED, OUT_OF_SCOPE)
5. Human approval gate compliance
Saves measured results to `eval_results_task3.csv`.
"""

import csv
from pathlib import Path
from agents import approve_scope_version, init_scope_db, run_meeting_to_scope_pipeline

TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"

def run_evaluations() -> list[dict]:
    init_scope_db()
    t1_text = (TRANSCRIPTS_DIR / "meeting_1_search.txt").read_text(encoding="utf-8")
    t2_text = (TRANSCRIPTS_DIR / "meeting_2_checkout.txt").read_text(encoding="utf-8")
    t3_text = (TRANSCRIPTS_DIR / "meeting_3_followup.txt").read_text(encoding="utf-8")

    models = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
    rows = []

    for model in models:
        proj_a = f"EVAL-CARE-{model}"
        proj_b = f"EVAL-BUILD-{model}"

        res_a = run_meeting_to_scope_pipeline(proj_a, "meeting_1_search.txt", t1_text, model_name=model)
        approve_scope_version(proj_a, res_a["version"], reviewer_name="Eval Reviewer")
        res_c = run_meeting_to_scope_pipeline(proj_a, "meeting_3_followup.txt", t3_text, model_name=model)
        res_b = run_meeting_to_scope_pipeline(proj_b, "meeting_2_checkout.txt", t2_text, model_name=model)

        reqs_a = {r["req_id"]: r for r in res_a["scope"]["deliverables"]}
        est_a = {t["req_id"]: t for t in res_a["estimates"]["tasks"]}
        reqs_b = {r["req_id"]: r for r in res_b["scope"]["deliverables"]}
        est_b = {t["req_id"]: t for t in res_b["estimates"]["tasks"]}
        diff_c = {c["req_id"]: c for c in (res_c["change_report"] or {}).get("changes", [])}

        checks = [
            ("SC-01", "Extract REQ-001 search filters from Meeting A", "REQ-001" in reqs_a, res_a["latency_ms"], res_a["cost_usd"] / 7),
            ("SC-02", "Classify REQ-001 search filters as built-in setting via Task 1", reqs_a.get("REQ-001", {}).get("feasibility_class") == "existing_configuration", res_a["latency_ms"], res_a["cost_usd"] / 7),
            ("SC-03", "Estimate REQ-001 built-in search filters at <= 4 hours", est_a.get("REQ-001", {}).get("likely_hours", 99) <= 4.0, res_a["latency_ms"], res_a["cost_usd"] / 7),
            ("SC-04", "Flag REQ-002 vague AI symptom search as unclear / needs_clarification", reqs_a.get("REQ-002", {}).get("feasibility_class") in ("needs_clarification", "custom_development"), res_a["latency_ms"], res_a["cost_usd"] / 7),
            ("SC-05", "Classify REQ-003 basic mobile settings in Meeting A as built-in", reqs_a.get("REQ-003", {}).get("feasibility_class") == "existing_configuration", res_a["latency_ms"], res_a["cost_usd"] / 7),
            ("SC-06", "Classify REQ-004 300x80 logo & favicon in Meeting A as built-in", reqs_a.get("REQ-004", {}).get("feasibility_class") == "existing_configuration", res_a["latency_ms"], res_a["cost_usd"] / 7),
            ("SC-07", "Generate open consultant questions for Meeting A", len(res_a["scope"]["open_questions_and_risks"]) >= 1, res_a["latency_ms"], res_a["cost_usd"] / 7),
            ("SC-08", "Meeting B: Classify signup field & 20% promo coupon as built-in", reqs_b.get("REQ-001", {}).get("feasibility_class") == "existing_configuration", res_b["latency_ms"], res_b["cost_usd"] / 6),
            ("SC-09", "Meeting B: Classify lead email template customization as built-in", reqs_b.get("REQ-002", {}).get("feasibility_class") == "existing_configuration", res_b["latency_ms"], res_b["cost_usd"] / 6),
            ("SC-10", "Meeting B: Classify Twilio SMS/WhatsApp alert as custom_development", reqs_b.get("REQ-003", {}).get("feasibility_class") == "custom_development", res_b["latency_ms"], res_b["cost_usd"] / 6),
            ("SC-11", "Meeting B: Classify native Stripe + force_ssl_checkout as built-in", reqs_b.get("REQ-004", {}).get("feasibility_class") == "existing_configuration", res_b["latency_ms"], res_b["cost_usd"] / 6),
            ("SC-12", "Meeting B: Flag Sensepass/Razorpay external gateway as non-native", reqs_b.get("REQ-005", {}).get("feasibility_class") in ("needs_clarification", "custom_development"), res_b["latency_ms"], res_b["cost_usd"] / 6),
            ("SC-13", "Meeting B: Estimate custom Twilio webhook higher than built-in email", est_b.get("REQ-003", {}).get("likely_hours", 0) > est_b.get("REQ-002", {}).get("likely_hours", 99), res_b["latency_ms"], res_b["cost_usd"] / 6),
            ("SC-14", "Meeting C Diff: Detect REQ-002 (AI symptom search) was REMOVED", diff_c.get("REQ-002", {}).get("change_type") == "REMOVED", res_c["latency_ms"], res_c["cost_usd"] / 7),
            ("SC-15", "Meeting C Diff: Detect REQ-003 (Mobile Sticky AJAX Drawer) was MODIFIED", diff_c.get("REQ-003", {}).get("change_type") == "MODIFIED", res_c["latency_ms"], res_c["cost_usd"] / 7),
            ("SC-16", "Meeting C Diff: Detect REQ-005 (Built-in CSV import of 2,200 doctors) as ADDED", diff_c.get("REQ-005", {}).get("change_type") == "ADDED", res_c["latency_ms"], res_c["cost_usd"] / 7),
            ("SC-17", "Meeting C Diff: Flag REQ-006 (Custom Texas Medical Board API) as OUT_OF_SCOPE", diff_c.get("REQ-006", {}).get("change_type") == "OUT_OF_SCOPE", res_c["latency_ms"], res_c["cost_usd"] / 7),
            ("SC-18", "Meeting C Diff: Require extra quotation for REQ-006 out-of-scope custom work", diff_c.get("REQ-006", {}).get("requires_extra_quote") is True, res_c["latency_ms"], res_c["cost_usd"] / 7),
            ("SC-19", "Meeting C Diff: Detect 2-week deadline shift (Nov 15 -> Nov 1)", (res_c["change_report"] or {}).get("deadline_changed") is True, res_c["latency_ms"], res_c["cost_usd"] / 7),
            ("SC-20", "Approval Gate: Unapproved follow-up proposal blocks client send by default", res_c["can_send_to_client"] is False, res_c["latency_ms"], res_c["cost_usd"] / 7),
        ]

        for cid, desc, passed, lat, cost in checks:
            rows.append(
                {
                    "task": "scope",
                    "case_id": cid,
                    "description": desc,
                    "model": model,
                    "quality_score": 1.0 if passed else 0.0,
                    "latency_ms": round(lat, 1),
                    "cost_usd": round(cost, 6),
                    "passed": passed,
                    "failure_reason": "" if passed else f"Failed check: {desc}",
                }
            )

    out_csv = Path(__file__).parent / "eval_results_task3.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} evaluation rows to {out_csv}")
    for m in models:
        m_rows = [r for r in rows if r["model"] == m]
        pass_rate = sum(1 for r in m_rows if r["passed"]) / len(m_rows) * 100
        avg_lat = sum(r["latency_ms"] for r in m_rows) / len(m_rows)
        total_cost = sum(r["cost_usd"] for r in m_rows)
        print(f"Model: {m:22s} | Pass Rate: {pass_rate:5.1f}% | Avg Latency: {avg_lat:6.1f}ms | Total Cost: ${total_cost:.5f}")
    return rows

if __name__ == "__main__":
    run_evaluations()
