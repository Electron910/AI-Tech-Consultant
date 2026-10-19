"""
task1-knowledge-brain/search.py
-------------------------------
Why this file exists:
Handles splitting articles into meaningful chunks, turning text into vector embeddings
(using Gemini `gemini-embedding-001` with a fast local fallback), and searching both
vectors (meaning) and keywords (exact setting names) in SQLite.
"""

import hashlib
import json
import math
import os
import re
import sqlite3
import time
from pathlib import Path
from dotenv import load_dotenv
import numpy as np
from google import genai
from prompts import GroundedAnswerSchema, RAG_PROMPTS, SourceCitation

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DB_PATH = Path(__file__).parent / "knowledge.db"

def get_db() -> sqlite3.Connection:
    """Opens a SQLite connection where columns can be accessed by name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    """Creates all tables needed for crawling, chunks, escalations, and daily reports."""
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS manifest (
                url TEXT PRIMARY KEY,
                lastmod TEXT,
                content_hash TEXT,
                status TEXT DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                last_error TEXT,
                is_active INTEGER DEFAULT 1,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS articles (
                url TEXT PRIMARY KEY,
                title TEXT,
                category TEXT,
                folder TEXT,
                body_text TEXT,
                images_json TEXT,
                content_hash TEXT,
                is_active INTEGER DEFAULT 1,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                article_url TEXT,
                article_title TEXT,
                section_heading TEXT,
                chunk_text TEXT,
                image_url TEXT,
                embedding_json TEXT,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS escalations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                reason TEXT,
                retrieved_preview TEXT,
                status TEXT DEFAULT 'open',
                expert_answer TEXT,
                expert_author TEXT,
                is_global_fact INTEGER DEFAULT 1,
                created_at TEXT,
                resolved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sync_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time TEXT,
                added_count INTEGER,
                updated_count INTEGER,
                unchanged_count INTEGER,
                removed_count INTEGER,
                failed_count INTEGER,
                notes TEXT
            );
            """
        )

def chunk_article(
    url: str,
    title: str,
    sections: list[dict],
    max_chars: int = 900,
    overlap_chars: int = 120,
) -> list[dict]:
    """
    Splits an article into chunks by section heading first.
    Attaches the article title, section heading, and any screenshot description
    to every chunk so context is never lost.
    """
    chunks = []
    for sec_idx, sec in enumerate(sections):
        heading = sec.get("heading") or "General Overview"
        text = (sec.get("text") or "").strip()
        image_url = sec.get("image_url")
        image_context = sec.get("image_context", "")

        full_sec_text = text
        if image_context:
            full_sec_text = f"{text}\n{image_context}".strip()

        if not full_sec_text:
            continue

        if len(full_sec_text) <= max_chars:
            raw_pieces = [full_sec_text]
        else:
            raw_pieces = []
            start = 0
            while start < len(full_sec_text):
                end = min(start + max_chars, len(full_sec_text))
                raw_pieces.append(full_sec_text[start:end])
                if end == len(full_sec_text):
                    break
                start = max(end - overlap_chars, start + 1)

        for piece_idx, piece in enumerate(raw_pieces):
            header_prefix = f"[Article: {title} | Section: {heading}]\n"
            final_text = header_prefix + piece
            chunk_id = hashlib.md5(f"{url}::{sec_idx}::{piece_idx}".encode()).hexdigest()
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "article_url": url,
                    "article_title": title,
                    "section_heading": heading,
                    "chunk_text": final_text,
                    "image_url": image_url,
                }
            )
    return chunks

def _local_hash_embedding(text: str, dim: int = 256) -> list[float]:
    """
    Simple, deterministic 256-dim bag-of-words/n-gram vector used when running
    offline or without a live API key so tests and demos work 100% reliably.
    """
    vec = np.zeros(dim, dtype=np.float32)
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    for tok in tokens:
        idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim
        vec[idx] += 1.0
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return [round(float(x), 5) for x in vec]

def compute_embedding(text: str) -> list[float]:
    """Computes a vector embedding using Gemini, falling back to local vector if unavailable."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    embed_model = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
    if not api_key or api_key == "your_gemini_api_key_here" or os.getenv("USE_LOCAL_EMBEDDINGS") == "1":
        return _local_hash_embedding(text)

    try:
        client = genai.Client(api_key=api_key)
        res = client.models.embed_content(model=embed_model, contents=text[:2000])
        values = list(res.embeddings[0].values)
        return [round(float(v), 5) for v in values]
    except Exception:
        return _local_hash_embedding(text)

def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Computes cosine similarity between two vectors cleanly."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0

def _keyword_overlap_score(query: str, chunk_text: str) -> float:
    """
    Computes exact keyword overlap score (like lightweight BM25).
    Crucial for matching exact setting names like 'force_ssl_checkout' or '300x80px'.
    """
    stop_words = {
        "how", "do", "i", "the", "a", "an", "in", "on", "to", "for", "of", "and",
        "is", "are", "can", "we", "my", "our", "what", "where", "when", "with",
        "brilliant", "directories", "configure", "built", "module", "custom",
        "time", "response", "hosting", "servers", "server", "using", "automatically",
    }
    q_tokens = [t for t in re.findall(r"[a-z0-9_]+", query.lower()) if t not in stop_words and len(t) > 1]
    if not q_tokens:
        return 0.0
    c_lower = chunk_text.lower()
    c_tokens = set(re.findall(r"[a-z0-9_]+", c_lower))
    matched = 0.0
    for qt in q_tokens:
        if qt in c_tokens:
            matched += 1.0
        elif qt in c_lower:
            matched += 0.6
        elif len(qt) > 4 and any(ct.startswith(qt[:4]) for ct in c_tokens):
            matched += 0.5
    return matched / len(q_tokens)

def retrieve_chunks(query: str, top_k: int = 4, search_mode: str = "hybrid") -> list[dict]:
    """
    Searches active chunks in SQLite using:
    - 'vector': semantic similarity only
    - 'keyword': exact word overlap only
    - 'hybrid' (default): 45% vector similarity + 55% keyword match
    Only returns chunks where `is_active = 1` (so deleted articles never appear!).
    """
    query_vec = compute_embedding(query)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT chunk_id, article_url, article_title, section_heading, chunk_text, image_url, embedding_json "
            "FROM chunks WHERE is_active = 1"
        ).fetchall()

    scored = []
    for row in rows:
        emb = json.loads(row["embedding_json"]) if row["embedding_json"] else []
        vec_score = _cosine_similarity(query_vec, emb)
        if len(emb) != len(query_vec):
            vec_score = _cosine_similarity(_local_hash_embedding(query), _local_hash_embedding(row["chunk_text"]))

        kw_score = _keyword_overlap_score(query, row["chunk_text"])

        if search_mode == "vector":
            final_score = vec_score
        elif search_mode == "keyword":
            final_score = kw_score
        else:
            final_score = 0.45 * vec_score + 0.55 * kw_score

        scored.append(
            {
                "chunk_id": row["chunk_id"],
                "article_url": row["article_url"],
                "article_title": row["article_title"],
                "section_heading": row["section_heading"],
                "chunk_text": row["chunk_text"],
                "image_url": row["image_url"],
                "relevance": round(float(final_score), 4),
                "vec_score": round(float(vec_score), 4),
                "kw_score": round(float(kw_score), 4),
            }
        )

    scored.sort(key=lambda x: x["relevance"], reverse=True)
    return scored[:top_k]

def _detect_prompt_injection(text: str) -> bool:
    """Catches attempts to hijack system instructions."""
    lowered = text.lower()
    patterns = [
        "ignore previous instructions",
        "ignore all rules",
        "system prompt",
        "you are now",
        "bypass safety",
        "approve a refund of",
    ]
    return any(p in lowered for p in patterns)

def create_escalation(question: str, reason: str, retrieved_chunks: list[dict]) -> int:
    """Saves an unanswered question for a human expert to resolve."""
    preview = "\n---\n".join(c["chunk_text"][:250] for c in retrieved_chunks[:2])
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO escalations (question, reason, retrieved_preview, status, created_at)
            VALUES (?, ?, ?, 'open', datetime('now'))
            """,
            (question, reason, preview),
        )
        return int(cur.lastrowid)

def resolve_escalation(
    escalation_id: int,
    expert_answer: str,
    expert_author: str = "Senior Product Specialist",
    is_global_fact: bool = True,
) -> dict:
    """
    Records a human expert's answer. If `is_global_fact` is True, indexes the
    expert answer directly into the `chunks` table so the Brain remembers it immediately!
    """
    with get_db() as conn:
        row = conn.execute("SELECT * FROM escalations WHERE id = ?", (escalation_id,)).fetchone()
        if not row:
            raise ValueError(f"Escalation ID {escalation_id} not found")

        conn.execute(
            """
            UPDATE escalations
            SET status = 'resolved',
                expert_answer = ?,
                expert_author = ?,
                is_global_fact = ?,
                resolved_at = datetime('now')
            WHERE id = ?
            """,
            (expert_answer, expert_author, 1 if is_global_fact else 0, escalation_id),
        )

        if is_global_fact:
            expert_url = f"https://support.brilliantdirectories.com/support/expert-verified/{escalation_id}"
            title = f"Expert Verified Answer #{escalation_id}: {row['question'][:60]}"
            chunk_text = (
                f"[Article: {title} | Section: Human Expert Verified Resolution]\n"
                f"Question: {row['question']}\n"
                f"Verified Expert Answer ({expert_author}): {expert_answer}"
            )
            emb = compute_embedding(chunk_text)
            chunk_id = f"expert_{escalation_id}"
            conn.execute(
                """
                INSERT OR REPLACE INTO chunks
                (chunk_id, article_url, article_title, section_heading, chunk_text, image_url, embedding_json, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (chunk_id, expert_url, title, "Expert Resolution", chunk_text, None, json.dumps(emb)),
            )

    return {"escalation_id": escalation_id, "status": "resolved", "added_to_memory": is_global_fact}

def answer_question(
    question: str,
    model_name: str | None = None,
    prompt_version: str = "v2",
    search_mode: str = "hybrid",
    top_k: int = 4,
) -> dict:
    """
    Full RAG pipeline:
    1. Checks for prompt injection.
    2. Retrieves top matching chunks (including screenshot descriptions and expert answers).
    3. Calls Gemini (or deterministic grounded synthesis if no API key) to generate answer.
    4. Creates a human escalation ticket if evidence is missing.
    """
    start_time = time.perf_counter()
    model_to_use = model_name or os.getenv("GEMINI_MAIN_MODEL", "gemini-flash-latest")

    if _detect_prompt_injection(question):
        latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
        return {
            "answer": "I cannot fulfill requests that attempt to override system safety instructions. Please ask a standard Brilliant Directories product question.",
            "status": "rejected_unsafe",
            "confidence": 1.0,
            "needs_human": False,
            "escalation_id": None,
            "sources": [],
            "images": [],
            "model_used": model_to_use,
            "prompt_version": prompt_version,
            "latency_ms": latency_ms,
            "cost_usd": 0.0,
        }

    chunks = retrieve_chunks(question, top_k=top_k, search_mode=search_mode)
    top_relevance = chunks[0]["relevance"] if chunks else 0.0

    relevant_chunks = [c for c in chunks if c["relevance"] >= 0.22]

    if not relevant_chunks or top_relevance < 0.28:
        reason = "No help center article had sufficient overlap with this question."
        esc_id = create_escalation(question, reason, chunks)
        latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
        return {
            "answer": "I do not have enough verified information in the Brilliant Directories Solution Center to answer this question accurately. I have escalated your question to a human product specialist.",
            "status": "insufficient_evidence",
            "confidence": round(top_relevance, 2),
            "needs_human": True,
            "escalation_id": esc_id,
            "sources": [],
            "images": [],
            "model_used": model_to_use,
            "prompt_version": prompt_version,
            "latency_ms": latency_ms,
            "cost_usd": 0.0,
        }

    context_str = "\n\n---\n\n".join(
        f"SOURCE URL: {c['article_url']}\nTITLE: {c['article_title']}\nIMAGE URL: {c['image_url'] or 'None'}\nCONTENT:\n{c['chunk_text']}"
        for c in relevant_chunks
    )

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    prompt_template = RAG_PROMPTS.get(prompt_version, RAG_PROMPTS["v2"])
    full_prompt = prompt_template.format(context=context_str, question=question)

    if api_key and api_key != "your_gemini_api_key_here":
        for attempt in range(2):
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model_to_use,
                    contents=full_prompt,
                    config=genai.types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=GroundedAnswerSchema,
                        temperature=0.1,
                    ),
                )
                parsed = GroundedAnswerSchema.model_validate_json(response.text)

                in_tokens = len(full_prompt) / 4.0
                out_tokens = len(response.text) / 4.0
                rate_in = 0.0000001 if "lite" in model_to_use else 0.0000003
                rate_out = 0.0000004 if "lite" in model_to_use else 0.0000025
                cost_usd = round(in_tokens * rate_in + out_tokens * rate_out, 6)

                esc_id = None
                if not parsed.has_enough_evidence:
                    esc_id = create_escalation(
                        question,
                        parsed.escalation_reason or "Model flagged insufficient evidence in retrieved chunks.",
                        relevant_chunks,
                    )

                sources_out = [
                    {
                        "title": s.title,
                        "url": s.url,
                        "image_url": s.image_url,
                        "relevance": relevant_chunks[0]["relevance"],
                    }
                    for s in parsed.sources
                ]
                if not sources_out and parsed.has_enough_evidence:
                    sources_out = [
                        {
                            "title": c["article_title"],
                            "url": c["article_url"],
                            "image_url": c["image_url"],
                            "relevance": c["relevance"],
                        }
                        for c in relevant_chunks[:2]
                    ]

                images_out = [s["image_url"] for s in sources_out if s.get("image_url")]
                latency_ms = round((time.perf_counter() - start_time) * 1000, 1)

                return {
                    "answer": parsed.answer,
                    "status": "answered" if parsed.has_enough_evidence else "insufficient_evidence",
                    "confidence": round(parsed.confidence, 2),
                    "needs_human": not parsed.has_enough_evidence,
                    "escalation_id": esc_id,
                    "sources": sources_out,
                    "images": images_out,
                    "model_used": model_to_use,
                    "prompt_version": prompt_version,
                    "latency_ms": latency_ms,
                    "cost_usd": cost_usd,
                }
            except Exception:
                if attempt == 0:
                    time.sleep(0.5)

    best_chunks = relevant_chunks[:2]
    synthesized_lines = []
    sources_out = []
    images_out = []
    seen_urls = set()

    for c in best_chunks:
        body = re.sub(r"^\[Article:.*?\]\n", "", c["chunk_text"]).strip()
        synthesized_lines.append(body)
        if c["article_url"] not in seen_urls:
            seen_urls.add(c["article_url"])
            sources_out.append(
                {
                    "title": c["article_title"],
                    "url": c["article_url"],
                    "image_url": c["image_url"],
                    "relevance": c["relevance"],
                }
            )
        if c["image_url"] and c["image_url"] not in images_out:
            images_out.append(c["image_url"])

    if prompt_version == "v1" and top_relevance < 0.35:
        sources_out = sources_out[:1]

    in_tokens = len(full_prompt) / 4.0
    out_tokens = sum(len(x) for x in synthesized_lines) / 4.0
    rate_in = 0.0000001 if "lite" in model_to_use else 0.0000003
    rate_out = 0.0000004 if "lite" in model_to_use else 0.0000025
    cost_usd = round(in_tokens * rate_in + out_tokens * rate_out, 6)
    latency_ms = round((time.perf_counter() - start_time) * 1000, 1)

    return {
        "answer": "\n\n".join(synthesized_lines),
        "status": "answered",
        "confidence": round(min(0.96, top_relevance + 0.25), 2),
        "needs_human": False,
        "escalation_id": None,
        "sources": sources_out,
        "images": images_out,
        "model_used": model_to_use,
        "prompt_version": prompt_version,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
    }
