"""
Why this file exists:
Implements the "20 consecutive drafts of the same kind sent without changing them" rule,
plus hard safety overrides so high-risk emails (refunds, quotes, complaints, new projects)
never go out without a human checking them.
"""

import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "inbox.db"

HIGH_RISK_BLOCKED_CATEGORIES = {
    "refund_or_cancellation",
    "complaint",
    "quote_request",
    "project_request",
}

ALL_CATEGORIES = [
    "how_to",
    "troubleshooting",
    "project_request",
    "refund_or_cancellation",
    "complaint",
    "quote_request",
    "follow_up",
]

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_autonomy_tables() -> None:
    """Creates tables for tracking the 20-streak counter, email reviews, and learned rules."""
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS category_streaks (
                category TEXT PRIMARY KEY,
                consecutive_unchanged INTEGER DEFAULT 0,
                total_approved INTEGER DEFAULT 0,
                total_edited INTEGER DEFAULT 0,
                total_rejected INTEGER DEFAULT 0,
                auto_send_enabled INTEGER DEFAULT 0,
                last_reset_reason TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS email_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT,
                sender_email TEXT,
                subject TEXT,
                original_body TEXT,
                predicted_category TEXT,
                risk_level TEXT,
                kb_status TEXT,
                kb_sources_json TEXT,
                generated_draft TEXT,
                final_sent_reply TEXT,
                was_edited INTEGER DEFAULT 0,
                approval_outcome TEXT,
                reviewer_note TEXT,
                model_used TEXT,
                prompt_version TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS learned_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                rule_text TEXT,
                source_email_id TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            );
            """
        )
        for cat in ALL_CATEGORIES:
            conn.execute(
                """
                INSERT OR IGNORE INTO category_streaks
                (category, consecutive_unchanged, total_approved, total_edited, total_rejected, auto_send_enabled, updated_at)
                VALUES (?, 0, 0, 0, 0, 0, datetime('now'))
                """,
                (cat,),
            )

def normalize_text(text: str) -> str:
    """Normalizes whitespace so we can check if the human changed even one word."""
    return re.sub(r"\s+", " ", (text or "").strip())

def is_draft_unchanged(generated_draft: str, final_sent_reply: str) -> bool:
    """Returns True ONLY if the final sent reply matches the AI draft character-for-character (ignoring extra spaces)."""
    return normalize_text(generated_draft) == normalize_text(final_sent_reply)

def record_human_decision(
    category: str,
    generated_draft: str,
    final_sent_reply: str,
    outcome: str,
    reason: str = "",
) -> dict:
    """
    Updates the consecutive-unchanged streak for `category`:
    - If `outcome == 'approved'` AND the text is completely unchanged: streak += 1.
    - Once streak >= 20 AND category is not in HIGH_RISK_BLOCKED_CATEGORIES: auto_send_enabled = 1.
    - If edited, rejected, or quality drops: streak resets to 0 and auto_send_enabled turns OFF (0).
    """
    init_autonomy_tables()
    unchanged = is_draft_unchanged(generated_draft, final_sent_reply)

    with get_db() as conn:
        row = conn.execute("SELECT * FROM category_streaks WHERE category = ?", (category,)).fetchone()
        if not row:
            current_streak = 0
            tot_app = tot_edit = tot_rej = 0
        else:
            current_streak = row["consecutive_unchanged"]
            tot_app = row["total_approved"]
            tot_edit = row["total_edited"]
            tot_rej = row["total_rejected"]

        if outcome == "approved" and unchanged:
            new_streak = current_streak + 1
            tot_app += 1
            reset_reason = None
        elif outcome == "approved" and not unchanged:
            new_streak = 0
            tot_edit += 1
            reset_reason = reason or "Draft text was modified before sending"
        elif outcome == "edited":
            new_streak = 0
            tot_edit += 1
            reset_reason = reason or "Human edited draft"
        else:
            new_streak = 0
            tot_rej += 1
            reset_reason = reason or f"Streak reset due to {outcome}"

        eligible_by_count = new_streak >= 20
        blocked_by_policy = category in HIGH_RISK_BLOCKED_CATEGORIES
        auto_send = 1 if (eligible_by_count and not blocked_by_policy) else 0

        conn.execute(
            """
            UPDATE category_streaks
            SET consecutive_unchanged = ?,
                total_approved = ?,
                total_edited = ?,
                total_rejected = ?,
                auto_send_enabled = ?,
                last_reset_reason = COALESCE(?, last_reset_reason),
                updated_at = datetime('now')
            WHERE category = ?
            """,
            (new_streak, tot_app, tot_edit, tot_rej, auto_send, reset_reason, category),
        )

    return get_category_autonomy_status(category)

def get_category_autonomy_status(category: str) -> dict:
    """Returns current streak, 20-threshold eligibility, and safety policy status."""
    init_autonomy_tables()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM category_streaks WHERE category = ?", (category,)).fetchone()
        if not row:
            return {"category": category, "consecutive_unchanged": 0, "auto_send_enabled": False}
        d = dict(row)
        d["auto_send_enabled"] = bool(d["auto_send_enabled"])
        d["blocked_by_safety_policy"] = category in HIGH_RISK_BLOCKED_CATEGORIES
        d["progress_to_20"] = f"{d['consecutive_unchanged']}/20"
        return d

def get_all_autonomy_statuses() -> list[dict]:
    init_autonomy_tables()
    return [get_category_autonomy_status(c) for c in ALL_CATEGORIES]
