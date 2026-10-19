"""
task3-meeting-to-scope/test_task3.py
------------------------------------
Unit tests for Task 3 (Meeting to Scope of Work):
- Verifies all 3 role-played transcripts exist.
- Verifies long transcript splitting preserves overlap.
- Verifies Meeting A -> Approval -> Meeting C follow-up diff catches REMOVED, MODIFIED, ADDED, and OUT_OF_SCOPE items.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.modules.pop("prompts", None)

from agents import (
    approve_scope_version,
    init_scope_db,
    run_meeting_to_scope_pipeline,
    split_long_transcript,
)

TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"

def test_three_transcripts_exist_and_split_cleanly():
    for name in ["meeting_1_search.txt", "meeting_2_checkout.txt", "meeting_3_followup.txt"]:
        p = TRANSCRIPTS_DIR / name
        assert p.exists()
        txt = p.read_text(encoding="utf-8")
        assert len(txt) > 500
        parts = split_long_transcript(txt, max_chars=800, overlap_chars=100)
        assert len(parts) >= 2

def test_meeting_a_to_c_baseline_approval_and_scope_diff():
    init_scope_db()
    t1 = (TRANSCRIPTS_DIR / "meeting_1_search.txt").read_text(encoding="utf-8")
    t3 = (TRANSCRIPTS_DIR / "meeting_3_followup.txt").read_text(encoding="utf-8")

    res_a = run_meeting_to_scope_pipeline("TEST-PROJ-1", "meeting_1_search.txt", t1)
    assert res_a["is_approved"] is False
    assert res_a["can_send_to_client"] is False

    app = approve_scope_version("TEST-PROJ-1", res_a["version"], "Senior Partner")
    assert app["can_send_to_client"] is True

    res_c = run_meeting_to_scope_pipeline("TEST-PROJ-1", "meeting_3_followup.txt", t3)
    cr = res_c["change_report"]
    assert cr is not None
    assert cr["deadline_changed"] is True

    change_types = {c["req_id"]: c["change_type"] for c in cr["changes"]}
    assert change_types.get("REQ-002") == "REMOVED"
    assert change_types.get("REQ-003") == "MODIFIED"
    assert change_types.get("REQ-005") == "ADDED"
    assert change_types.get("REQ-006") == "OUT_OF_SCOPE"
