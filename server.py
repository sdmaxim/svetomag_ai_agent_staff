"""
Web server: customer chat page + admin page for the difficult-questions loop.

    /                         customer chat (web/chat.html)
    /admin                    admin page    (web/admin.html)
    POST /api/chat            {"session_id"?, "message"} -> {"session_id", "reply", "trace"}
    GET  /api/admin/questions?status=open|answered|rejected|all
    POST /api/admin/questions/{id}/answer   {"answer"}
    POST /api/admin/questions/{id}/reject

Built on Starlette (already installed with crewai, so no new dependency).
Admin access: if the ADMIN_TOKEN environment variable is set, every admin request needs the
header X-Admin-Token; if it is not set, the admin API only answers requests from this computer.

Usage (from the support_agent folder):
    .\\run.ps1 web            then open http://127.0.0.1:8000  and  http://127.0.0.1:8000/admin
"""
import os
import secrets
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

load_dotenv()

import knowledge  # noqa: E402
from agent import SupportSession  # noqa: E402

WEB = Path(__file__).parent / "web"
MAX_MESSAGE = 1000          # characters per customer message
MAX_SESSIONS = 200
SESSION_TTL = 30 * 60       # a conversation is forgotten after 30 minutes without messages

_sessions: dict[str, dict] = {}     # session_id -> {"session", "lock", "last"}
_sessions_lock = threading.Lock()


def _get_session(session_id: str | None) -> tuple[str, dict]:
    now = time.time()
    with _sessions_lock:
        for sid in [s for s, v in _sessions.items() if now - v["last"] > SESSION_TTL]:
            del _sessions[sid]
        if session_id in _sessions:
            entry = _sessions[session_id]
        else:
            if len(_sessions) >= MAX_SESSIONS:   # drop the oldest conversation
                del _sessions[min(_sessions, key=lambda s: _sessions[s]["last"])]
            session_id = secrets.token_urlsafe(16)
            entry = {"session": SupportSession(), "lock": threading.Lock(), "last": now}
            _sessions[session_id] = entry
        entry["last"] = now
        return session_id, entry


def _chat_turn(entry: dict, message: str) -> dict:
    s: SupportSession = entry["session"]
    with entry["lock"]:   # one message at a time per conversation
        calls_before, skills_before = len(s.log.calls), len(s.log.skills_used)
        blocked_before, fallbacks_before = s.blocked_drafts, s.fallbacks
        reply = s.ask(message)
        new_calls = s.log.calls[calls_before:]
        return {
            "reply": reply,
            "trace": {   # how the agent produced this answer -- shown under the reply on the demo page
                "tools": [{"tool": c["tool"], "args": c["args"], "results": len(c["ids"])}
                          for c in new_calls if c["tool"] != "load_skill"],
                "skills": s.log.skills_used[skills_before:],
                "blocked_drafts": s.blocked_drafts - blocked_before,
                "fallback": s.fallbacks > fallbacks_before,
                "handed_to_specialist": any(c["tool"] == "save_difficult_question" for c in new_calls),
            },
        }


async def chat(request: Request):
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse({"error": "send JSON: {\"message\": \"...\"}"}, status_code=400)
    message = str(body.get("message", "")).strip()
    if not message:
        return JSONResponse({"error": "empty message"}, status_code=400)
    if len(message) > MAX_MESSAGE:
        return JSONResponse({"error": f"message too long (max {MAX_MESSAGE} characters)"}, status_code=400)
    session_id, entry = _get_session(body.get("session_id"))
    try:
        result = await run_in_threadpool(_chat_turn, entry, message)
    except Exception as e:  # never show a stack trace to a customer
        print(f"[chat error] {type(e).__name__}: {e}")
        return JSONResponse({"session_id": session_id, "error": "Sorry, something went wrong. Please try again."},
                            status_code=500)
    return JSONResponse({"session_id": session_id, **result})


def _admin_allowed(request: Request) -> bool:
    token = os.environ.get("ADMIN_TOKEN")
    if token:
        return secrets.compare_digest(request.headers.get("x-admin-token", ""), token)
    return request.client is not None and request.client.host in ("127.0.0.1", "::1", "localhost", "testclient")


def _public(q: dict) -> dict:
    return {k: v for k, v in q.items() if k != "embedding"}


async def admin_questions(request: Request):
    if not _admin_allowed(request):
        return JSONResponse({"error": "admin access denied"}, status_code=403)
    status = request.query_params.get("status", "open")
    items = knowledge.load()
    if status != "all":
        items = [q for q in items if q["status"] == status]
    items.sort(key=lambda q: (-q["times_asked"], q["id"]))
    return JSONResponse({"questions": [_public(q) for q in items]})


async def admin_answer(request: Request):
    if not _admin_allowed(request):
        return JSONResponse({"error": "admin access denied"}, status_code=403)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    answer = str(body.get("answer", "")).strip()
    if not answer:
        return JSONResponse({"error": "empty answer"}, status_code=400)
    try:
        q = knowledge.answer_question(int(request.path_params["qid"]), answer)
    except KeyError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return JSONResponse({"question": _public(q)})


async def admin_reject(request: Request):
    if not _admin_allowed(request):
        return JSONResponse({"error": "admin access denied"}, status_code=403)
    try:
        q = knowledge.reject_question(int(request.path_params["qid"]))
    except KeyError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return JSONResponse({"question": _public(q)})


async def page_chat(request: Request):
    return FileResponse(WEB / "chat.html")


async def page_admin(request: Request):
    return FileResponse(WEB / "admin.html")


app = Starlette(routes=[
    Route("/", page_chat),
    Route("/admin", page_admin),
    Route("/api/chat", chat, methods=["POST"]),
    Route("/api/admin/questions", admin_questions),
    Route("/api/admin/questions/{qid:int}/answer", admin_answer, methods=["POST"]),
    Route("/api/admin/questions/{qid:int}/reject", admin_reject, methods=["POST"]),
    Mount("/static", StaticFiles(directory=WEB), name="static"),
])
