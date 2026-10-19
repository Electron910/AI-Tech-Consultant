"""
task2-inbox-agent/test_task2.py
-------------------------------
Unit tests for Task 2 (The Inbox Agent):
- Verifies 50 realistic emails exist across all 7 categories.
- Verifies the 20-consecutive-unchanged approval streak and safety reset.
- Verifies high-risk categories are blocked from unsupervised auto-send even at 20.
- Verifies learning from human edits and Undo toggle.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.modules.pop("prompts", None)

from agent import get_active_learned_rules, learn_from_human_edit, toggle_learned_rule
from autonomy import init_autonomy_tables, record_human_decision

def test_50_emails_dataset_and_categories():
    emails_path = Path(__file__).parent / "emails_50.json"
    emails = json.loads(emails_path.read_text(encoding="utf-8"))
    assert len(emails) >= 50
    categories = {e["expected_category"] for e in emails}
    expected = {
        "how_to",
        "troubleshooting",
        "project_request",
        "refund_or_cancellation",
        "complaint",
        "quote_request",
        "follow_up",
    }
    assert expected.issubset(categories)

def test_20_consecutive_unchanged_rule_and_reset():
    init_autonomy_tables()
    draft = "Hi Megan, upload your logo under Settings -> Design Settings -> General (300x80px)."

    status = record_human_decision("how_to", draft, draft + " Edited!", "edited")
    assert status["consecutive_unchanged"] == 0
    assert status["auto_send_enabled"] is False

    for _ in range(19):
        status = record_human_decision("how_to", draft, draft, "approved")
    assert status["consecutive_unchanged"] == 19
    assert status["auto_send_enabled"] is False

    status = record_human_decision("how_to", draft, draft, "approved")
    assert status["consecutive_unchanged"] == 20
    assert status["auto_send_enabled"] is True

    status = record_human_decision("how_to", draft, draft + " Wait, clear cache too.", "edited")
    assert status["consecutive_unchanged"] == 0
    assert status["auto_send_enabled"] is False

def test_high_risk_refund_category_never_auto_sends_even_at_20():
    init_autonomy_tables()
    draft = "Your refund request has been escalated to our Billing Manager."
    status = {}
    for _ in range(21):
        status = record_human_decision("refund_or_cancellation", draft, draft, "approved")
    assert status["consecutive_unchanged"] >= 20
    assert status["blocked_by_safety_policy"] is True
    assert status["auto_send_enabled"] is False

def test_human_edit_learning_and_undo():
    init_autonomy_tables()
    orig = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6"
    edited = "Short 1-line direct answer."
    learned = learn_from_human_edit("EM-001", "how_to", orig, edited)
    assert learned is not None
    rule_id = learned["id"]

    active_ids = [r["id"] for r in get_active_learned_rules("how_to")]
    assert rule_id in active_ids

    toggle_learned_rule(rule_id, False)
    active_ids_after = [r["id"] for r in get_active_learned_rules("how_to")]
    assert rule_id not in active_ids_after
