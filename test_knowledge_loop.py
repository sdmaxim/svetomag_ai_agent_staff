"""
End-to-end test of the difficult-questions loop, graded by code:

 1. a question the agent cannot answer is saved for a specialist
 2. the same question in other words is counted, not duplicated
 3. a human answers it (like admin.py answer ...)
 4. a new customer asking the same thing gets the human's answer, nothing new is saved
 5. a RELATED but different question (another country) must NOT reuse that answer
 6. an unrelated difficult question is saved as a new one
 7. a normal product question saves nothing

Uses its own temporary questions file, so real customer questions are never touched.

Usage (from the support_agent folder):
    .\\run.ps1 test knowledge
"""
import os
import re
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp()) / "questions.json"
os.environ["KNOWLEDGE_FILE"] = str(TMP)

import knowledge  # noqa: E402  (after KNOWLEDGE_FILE is set)
from agent import SupportSession  # noqa: E402
from answer_check import check_answer  # noqa: E402

HUMAN_ANSWER = "Delivery within the Netherlands takes 2-3 working days. Orders over €50 ship for free."
HANDOFF_RE = re.compile(r"specialist|colleague|our team|pass(?:ed)? (?:this|your question|it)|forward", re.I)
NL_TIME_RE = re.compile(r"2\s*(?:-|–|to)\s*3 (?:working )?days", re.I)

results = []


def step(name, ok, detail=""):
    ok = bool(ok)   # conditions may be re.Match objects
    results.append(ok)
    print(f"\n{'PASS' if ok else 'FAIL'}  {name}" + (f"\n        {detail}" if detail and not ok else ""), flush=True)


def ask(question):
    s = SupportSession()
    reply = s.ask(question)
    problems = check_answer(reply, s.log)
    print(f"\n   customer: {question}\n   agent:    {reply[:300]}", flush=True)
    return s, reply, problems


def open_questions():
    return [q for q in knowledge.load() if q["status"] == "open"]


# 1. unknown -> saved
s, reply, probs = ask("How long does delivery to Amsterdam take?")
step("1. unknown question is saved for a specialist",
     len(open_questions()) == 1 and HANDOFF_RE.search(reply) and not NL_TIME_RE.search(reply) and not probs,
     f"open={len(open_questions())}, reply={reply[:120]}, check={probs}")

# 2. same question, other words -> counted
s, reply, probs = ask("What is the shipping time to Amsterdam?")
q = open_questions()
step("2. same question in other words is counted, not duplicated",
     len(q) == 1 and q[0]["times_asked"] == 2, f"open={[(x['question'], x['times_asked']) for x in q]}")

# 3. a human answers
knowledge.answer_question(q[0]["id"], HUMAN_ANSWER)
step("3. human answer stored", knowledge.load()[0]["status"] == "answered")

# 4. new customer, same topic -> human answer used, nothing saved
s, reply, probs = ask("How many days does shipping to Rotterdam take?")
step("4. a new customer gets the human answer (and nothing new is saved)",
     NL_TIME_RE.search(reply) and not s.log.saved_questions and not probs,
     f"saved={s.log.saved_questions}, check={probs}, reply={reply[:150]}")

# 5. related but different -> must not reuse the NL answer as if it were about Germany
s, reply, probs = ask("Do you deliver to Germany, and how long does it take?")
misused = NL_TIME_RE.search(reply) and not re.search(r"netherlands", reply, re.I)
step("5. related but different question (Germany) does NOT reuse the Netherlands answer",
     bool(s.log.saved_questions) and not misused and not probs,
     f"saved={s.log.saved_questions}, misused={bool(misused)}, reply={reply[:150]}")

# 6. unrelated difficult question -> new entry
before = len(open_questions())
s, reply, probs = ask("Can I use your LED strips inside a sauna?")
step("6. unrelated difficult question is saved as a new one",
     len(open_questions()) == before + 1 and HANDOFF_RE.search(reply),
     f"open before={before}, after={len(open_questions())}, reply={reply[:120]}")

# 7. product question -> nothing saved
s, reply, probs = ask("Do you have E14 LED candle bulbs?")
step("7. a normal product question saves nothing", not s.log.saved_questions and not probs,
     f"saved={s.log.saved_questions}, check={probs}")

print(f"\n{sum(results)}/{len(results)} passed")
print("\nquestions file after the test:")
for q in knowledge.load():
    print(f"  #{q['id']} [{q['status']}] x{q['times_asked']}  {q['question']}  -> {q['answer'] or ''}")
