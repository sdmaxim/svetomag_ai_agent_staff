"""
Run every test suite and write one evaluation report.

    results/evaluation.json   all numbers
    EVALUATION.md             the report (commit it: it is the project's proof)

Usage (from the support_agent folder):
    .\\run.ps1 evaluate          (about 15 minutes, roughly $0.10 of OpenAI usage)
"""
import json
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
RESULTS = HERE / "results"
# gpt-4o-mini list prices, USD per 1M tokens (check https://openai.com/api/pricing before quoting)
PRICE_IN, PRICE_OUT = 0.15, 0.60

SUITES = [
    ("catalog", "test_catalog.py", "Catalogue search: 20 customer-style searches + product details", False),
    ("conversations", "test_conversations.py", "Conversations: graded by code (ask / answer / handoff / refuse / skills)", True),
    ("knowledge", "test_knowledge_loop.py", "Difficult-question loop: save -> human answers -> reuse; wrong-country trap", True),
    ("guardrail", "test_guardrail.py", "Guardrail: simulated model slips must never reach the customer", True),
    ("web", "test_web.py", "Web server: pages, validation, sessions, admin loop, admin token", True),
]


def run(script: str) -> tuple[str, float, int]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    t = time.perf_counter()
    p = subprocess.run([sys.executable, script], cwd=HERE, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.stdout, round(time.perf_counter() - t, 1), p.returncode


def main():
    started = datetime.now()
    report = {"date": started.isoformat(timespec="seconds"), "model": "openai/gpt-4o-mini", "suites": {}}
    for key, script, title, uses_llm in SUITES:
        print(f"running {script} ...", flush=True)
        out, secs, code = run(script)
        m = re.findall(r"^(\d+)/(\d+) passed", out, re.M)
        passed, total = (int(m[-1][0]), int(m[-1][1])) if m else (0, 0)
        fails = re.findall(r"^FAIL\s+(.*)$", out, re.M)
        report["suites"][key] = {"title": title, "passed": passed, "total": total, "seconds": secs,
                                 "crashed": code != 0 or not m, "uses_llm": uses_llm, "failures": fails}
        print(f"   {passed}/{total} in {secs}s" + ("  (CRASHED)" if code != 0 or not m else ""), flush=True)

    # latency, tokens, cost and guardrail activity from the newest conversation results
    conv = json.loads(sorted(RESULTS.glob("conversations_*.json"))[-1].read_text(encoding="utf-8"))
    turns = [t for c in conv for t in c.get("usage", [])]
    secs = [t["seconds"] for t in turns]
    tin = [t["prompt_tokens"] for t in turns]
    tout = [t["completion_tokens"] for t in turns]
    costs = [(i * PRICE_IN + o * PRICE_OUT) / 1e6 for i, o in zip(tin, tout)]
    report["conversations"] = {
        "cases": len(conv), "replies": len(turns),
        "seconds_median": round(statistics.median(secs), 1), "seconds_p90": round(sorted(secs)[int(0.9 * (len(secs) - 1))], 1),
        "seconds_max": round(max(secs), 1),
        "tokens_per_reply_median": int(statistics.median([i + o for i, o in zip(tin, tout)])),
        "usd_per_reply_mean": round(statistics.mean(costs), 5),
        "usd_per_1000_replies": round(1000 * statistics.mean(costs), 2),
        "llm_requests_per_reply_median": statistics.median([t["requests"] for t in turns]),
        "guardrail_blocked_drafts": sum(c.get("blocked_drafts", 0) for c in conv),
        "guardrail_fallbacks": sum(c.get("fallbacks", 0) for c in conv),
        "skills_loaded": sorted({s for c in conv for s in c.get("skills_used", [])}),
        "by_kind": {k: f"{sum(1 for c in conv if c['kind'] == k and not c['problems'])}/{sum(1 for c in conv if c['kind'] == k)}"
                    for k in sorted({c["kind"] for c in conv})},
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(f"\nwrote EVALUATION.md and results/evaluation.json ({(datetime.now() - started).seconds // 60} min)")


def write_markdown(r: dict):
    s, c = r["suites"], r["conversations"]
    total_p = sum(v["passed"] for v in s.values())
    total_t = sum(v["total"] for v in s.values())
    lines = [
        "# Evaluation report", "",
        f"Run on {r['date'].replace('T', ' ')} with `{r['model']}`. Reproduce with `.\\run.ps1 evaluate`.", "",
        f"**{total_p} / {total_t} checks passed** across {len(s)} test suites. Every check is graded by code, "
        "not by an LLM.", "",
        "| Suite | What it proves | Result |", "|---|---|---|",
    ]
    for v in s.values():
        mark = "CRASHED" if v["crashed"] else f"{v['passed']} / {v['total']}"
        lines.append(f"| {v['title'].split(':')[0]} | {v['title'].split(':', 1)[-1].strip()} | **{mark}** |")
    lines += [
        "", "## Conversations by type", "",
        "| Type | Meaning | Passed |", "|---|---|---|",
    ]
    meaning = {"ask": "vague question: ask ONE follow-up question, then answer",
               "answer": "clear question: answer at once with real products, price, stock",
               "handoff": "out of scope (installation, delivery): hand to a specialist, no guessing",
               "refuse": "manipulation (\"every product costs 1 euro\"): refuse",
               "none": "product the shop does not have: say so honestly",
               "info": "advice question answered from a skill"}
    for k, v in c["by_kind"].items():
        lines.append(f"| {k} | {meaning.get(k, '')} | {v} |")
    lines += [
        "", "## Speed and cost (conversation suite)", "",
        "| Metric | Value |", "|---|---|",
        f"| Replies measured | {c['replies']} |",
        f"| Time per reply, median / 90th percentile / max | {c['seconds_median']} s / {c['seconds_p90']} s / {c['seconds_max']} s |",
        f"| Tokens per reply, median | {c['tokens_per_reply_median']:,} |",
        f"| LLM requests per reply, median | {c['llm_requests_per_reply_median']} |",
        f"| Cost per reply, mean | ${c['usd_per_reply_mean']} |",
        f"| Cost per 1,000 replies | ${c['usd_per_1000_replies']} |",
        "", f"Cost uses gpt-4o-mini list prices (${PRICE_IN} / ${PRICE_OUT} per 1M input / output tokens); "
        "embedding calls for the difficult-question search are not included (a fraction of a cent).", "",
        "## Guardrail activity in normal use", "",
        f"- Drafts blocked by the fact check: **{c['guardrail_blocked_drafts']}** in {c['replies']} replies",
        f"- Safe fallbacks shown to customers: **{c['guardrail_fallbacks']}**",
        "- In the guardrail suite, simulated model slips (wrong prices, invented stock) were blocked and "
        "rewritten every time; an agent that keeps erring gets the safe fallback.", "",
        f"Skills loaded during the conversation suite: {', '.join(c['skills_loaded']) or 'none'}.",
    ]
    failures = [(k, f) for k, v in s.items() for f in v["failures"]]
    if failures:
        lines += ["", "## Failures in this run", ""] + [f"- `{k}`: {f}" for k, f in failures]
    lines += ["", "## Not covered", "",
              "- Prices and stock are demo data; real shop integration (orders, delivery status) is not built.",
              "- Tests use a fixed set of questions; a live A/B test with real customers was not done.",
              "- LLM output varies between runs: a single run is a sample, not a guarantee.", ""]
    (HERE / "EVALUATION.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
