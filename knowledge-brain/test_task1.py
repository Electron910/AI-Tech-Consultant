"""
task1-knowledge-brain/test_task1.py
-----------------------------------
Unit and integration tests for Task 1 (The Knowledge Brain).
Run with: pytest task1-knowledge-brain/test_task1.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from crawler import SEED_ARTICLES, _save_article_and_chunks, deactivate_article, seed_initial_knowledge_base
from search import answer_question, init_db, resolve_escalation, retrieve_chunks

def test_seed_idempotency_and_retrieval():
    """Re-running ingestion on unchanged articles must not duplicate chunks."""
    init_db()
    first = seed_initial_knowledge_base()
    second = seed_initial_knowledge_base()
    assert second["unchanged"] >= len(SEED_ARTICLES)

    chunks = retrieve_chunks("What is the recommended website logo size?")
    assert len(chunks) > 0
    assert "300px" in chunks[0]["chunk_text"]

def test_screenshot_details_are_searchable():
    """Facts inside a screenshot description (like force_ssl_checkout) must be answered and cited."""
    res = answer_question("Which Advanced Setting is required in the screenshot for Stripe Live Mode?")
    assert res["status"] == "answered"
    assert "force_ssl_checkout" in res["answer"]
    assert len(res["sources"]) >= 1

def test_removed_article_disappears_from_answers():
    """When an article is deactivated, its chunks must stop appearing in search results."""
    target = SEED_ARTICLES[-1]
    deactivate_article(target["url"])
    chunks = retrieve_chunks("How many sub-accounts with Multi-Member Manager Add-On?")
    assert all(c["article_url"] != target["url"] for c in chunks)
    _save_article_and_chunks(target)

def test_unanswered_question_escalates_and_learns_from_human():
    """Unsupported questions must create a human escalation, and resolving it must teach the Brain."""
    from search import get_db
    with get_db() as conn:
        conn.execute("DELETE FROM chunks WHERE chunk_id LIKE 'expert_%'")
    q = "What is the custom SLA response time for Platinum Enterprise hosting?"
    res1 = answer_question(q)
    assert res1["status"] == "insufficient_evidence"
    assert res1["needs_human"] is True
    esc_id = res1["escalation_id"]
    assert esc_id is not None

    resolve_escalation(
        escalation_id=esc_id,
        expert_answer="Platinum Enterprise hosting includes a guaranteed 15-minute 24/7 SLA response time.",
        is_global_fact=True,
    )

    res2 = answer_question(q)
    assert res2["status"] == "answered"
    assert "15-minute" in res2["answer"]

    with get_db() as conn:
        conn.execute("DELETE FROM chunks WHERE chunk_id LIKE 'expert_%'")
