"""
Web server tests (Starlette TestClient - no browser, no real network):

 1. pages and static files are served
 2. bad input is rejected (empty, too long, not JSON)
 3. a 2-turn conversation keeps its session: follow-up question, then real products
 4. the difficult-question loop through the web API: handed over -> admin answers -> reused
 5. admin protection: with ADMIN_TOKEN set, requests without the token are refused

Usage (from the support_agent folder):
    .\\run.ps1 test web
"""
import os
import tempfile
from pathlib import Path

os.environ["KNOWLEDGE_FILE"] = str(Path(tempfile.mkdtemp()) / "questions.json")
os.environ.pop("ADMIN_TOKEN", None)

from starlette.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from answer_check import check_answer  # noqa: E402

client = TestClient(server.app)
results = []


def step(name, ok, detail=""):
    ok = bool(ok)
    results.append(ok)
    print(f"\n{'PASS' if ok else 'FAIL'}  {name}" + (f"\n        {detail}" if detail and not ok else ""), flush=True)


# 1. pages
r1, r2, r3 = client.get("/"), client.get("/admin"), client.get("/static/style.css")
step("1. chat page, admin page and stylesheet are served",
     r1.status_code == r2.status_code == r3.status_code == 200 and "Svetomag" in r1.text and "Difficult" in r2.text)

# 2. bad input
bad = [client.post("/api/chat", json={"message": "  "}).status_code,
       client.post("/api/chat", json={"message": "x" * 1001}).status_code,
       client.post("/api/chat", content="not json", headers={"Content-Type": "application/json"}).status_code]
step("2. empty, too long and non-JSON messages are rejected with 400", bad == [400, 400, 400], f"got {bad}")

# 3. two turns, one session
a = client.post("/api/chat", json={"message": "I need a new bulb."}).json()
sid = a.get("session_id")
b = client.post("/api/chat", json={"session_id": sid, "message": "E27, LED, warm light please."}).json()
log = server._sessions[sid]["session"].log
print(f"\n   turn 1: {a.get('reply', '')[:100]}\n   turn 2: {b.get('reply', '')[:100]}\n   trace 2: {b.get('trace')}")
step("3. a follow-up question first, then products in the SAME session, fact-checked",
     sid and b.get("session_id") == sid and "?" in a["reply"] and "€" in b["reply"]
     and any(t["tool"] == "search_products" for t in b["trace"]["tools"]) and not check_answer(b["reply"], log),
     f"a={a}, b={str(b)[:300]}")

# 4. difficult question loop via the API
c = client.post("/api/chat", json={"message": "Do you offer a warranty on LED bulbs?"}).json()
open_q = client.get("/api/admin/questions?status=open").json()["questions"]
step("4a. a difficult question is handed to a specialist and appears in the admin list",
     c["trace"]["handed_to_specialist"] and len(open_q) == 1 and "embedding" not in open_q[0],
     f"trace={c.get('trace')}, open={open_q}")
qid = open_q[0]["id"] if open_q else 0
ans = client.post(f"/api/admin/questions/{qid}/answer", json={"answer": "All LED bulbs have a 2-year warranty."})
answered = client.get("/api/admin/questions?status=answered").json()["questions"]
step("4b. the admin answers it through the API", ans.status_code == 200 and len(answered) == 1)
d = client.post("/api/chat", json={"message": "Is there a warranty for your LED lamps?"}).json()
print(f"\n   reused answer: {d.get('reply', '')[:160]}")
step("4c. a NEW customer gets the specialist's answer", "2-year" in d["reply"] and not d["trace"]["handed_to_specialist"],
     f"reply={d.get('reply')}")
step("4d. answering an unknown question id gives 404 and an empty answer gives 400",
     client.post("/api/admin/questions/999/answer", json={"answer": "x"}).status_code == 404
     and client.post(f"/api/admin/questions/{qid}/answer", json={"answer": " "}).status_code == 400)

# 5. admin token
os.environ["ADMIN_TOKEN"] = "test-secret"
no_token = client.get("/api/admin/questions").status_code
wrong = client.get("/api/admin/questions", headers={"X-Admin-Token": "nope"}).status_code
right = client.get("/api/admin/questions", headers={"X-Admin-Token": "test-secret"}).status_code
os.environ.pop("ADMIN_TOKEN")
step("5. with ADMIN_TOKEN set: no token 403, wrong token 403, right token 200",
     (no_token, wrong, right) == (403, 403, 200), f"got {(no_token, wrong, right)}")

print(f"\n{sum(results)}/{len(results)} passed")
