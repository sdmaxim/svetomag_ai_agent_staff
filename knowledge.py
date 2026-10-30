"""
The difficult-questions loop: questions the agent could not answer, and the answers humans wrote.

    knowledge/questions.json   one entry per question:
        id, question, reason, status ("open" | "answered" | "rejected"), times_asked,
        answer, answered_at, created_at, last_asked_at, embedding

Matching is by meaning (OpenAI embeddings + cosine similarity), so "How long does delivery
take?" finds "What is the shipping time?". The agent still has to judge whether a found
answer really fits (an answer about the Netherlands must not be reused for Germany).

The file path can be overridden with the KNOWLEDGE_FILE environment variable (used by tests).
"""
import json
import math
import os
import threading
from datetime import datetime
from pathlib import Path

from openai import OpenAI

EMBED_MODEL = "text-embedding-3-small"
MATCH_MIN = 0.40        # measured: same topic, other city 0.66; other country 0.45 -> the agent must judge
DUPLICATE_MIN = 0.85    # an open question this similar is the same question asked again

_lock = threading.Lock()
_client = None


def _path() -> Path:
    return Path(os.environ.get("KNOWLEDGE_FILE", Path(__file__).parent / "knowledge" / "questions.json"))


def _embed(text: str) -> list[float]:
    global _client
    _client = _client or OpenAI()
    return _client.embeddings.create(model=EMBED_MODEL, input=text.strip()[:2000]).data[0].embedding


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1.0)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load() -> list[dict]:
    p = _path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def _save(items: list[dict]):
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)   # atomic: a crash never leaves a half-written file


def search_answered(question: str, limit: int = 3) -> list[dict]:
    """Human answers to questions similar in meaning, best first (without embeddings)."""
    items = [q for q in load() if q["status"] == "answered"]
    if not items:
        return []
    v = _embed(question)
    scored = sorted(((round(_cosine(v, q["embedding"]), 3), q) for q in items), key=lambda t: -t[0])
    return [{"id": q["id"], "similarity": s, "question": q["question"], "answer": q["answer"]}
            for s, q in scored[:limit] if s >= MATCH_MIN]


def save_question(question: str, reason: str = "") -> dict:
    """Store a question for a human. The same question asked again only raises times_asked."""
    v = _embed(question)
    with _lock:
        items = load()
        for q in items:
            if q["status"] == "open" and _cosine(v, q["embedding"]) >= DUPLICATE_MIN:
                q["times_asked"] += 1
                q["last_asked_at"] = _now()
                _save(items)
                return {"id": q["id"], "status": "already waiting for a specialist", "times_asked": q["times_asked"]}
        new = {"id": max((q["id"] for q in items), default=0) + 1, "question": question.strip(),
               "reason": reason.strip(), "status": "open", "times_asked": 1, "answer": None,
               "answered_at": None, "created_at": _now(), "last_asked_at": _now(), "embedding": v}
        items.append(new)
        _save(items)
        return {"id": new["id"], "status": "saved for a specialist", "times_asked": 1}


def answer_question(qid: int, answer: str) -> dict:
    with _lock:
        items = load()
        q = next((q for q in items if q["id"] == qid), None)
        if q is None:
            raise KeyError(f"no question with id {qid}")
        q.update(status="answered", answer=answer.strip(), answered_at=_now())
        _save(items)
        return q


def seed_if_empty(seed_file: Path) -> int:
    """Load example specialist answers when there is no questions file yet (e.g. a fresh cloud host).
    Never touches an existing file. Returns how many answers were added."""
    if not seed_file.exists():
        return 0
    with _lock:
        if load():
            return 0
        items = []
        for i, s in enumerate(json.loads(seed_file.read_text(encoding="utf-8")), 1):
            items.append({"id": i, "question": s["question"], "reason": "demo answer loaded at start-up",
                          "status": "answered", "times_asked": 0, "answer": s["answer"], "answered_at": _now(),
                          "created_at": _now(), "last_asked_at": _now(), "embedding": _embed(s["question"])})
        _save(items)
        return len(items)


def reject_question(qid: int) -> dict:
    with _lock:
        items = load()
        q = next((q for q in items if q["id"] == qid), None)
        if q is None:
            raise KeyError(f"no question with id {qid}")
        q.update(status="rejected", answered_at=_now())
        _save(items)
        return q
