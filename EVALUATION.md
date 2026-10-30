# Evaluation report

Run on 2026-10-28 23:24:46 with `openai/gpt-4o-mini`. Reproduce with `.\run.ps1 evaluate`.

**70 / 70 checks passed** across 5 test suites. Every check is graded by code, not by an LLM.

| Suite | What it proves | Result |
|---|---|---|
| Catalogue search | 20 customer-style searches + product details | **21 / 21** |
| Conversations | graded by code (ask / answer / handoff / refuse / skills) | **26 / 26** |
| Difficult-question loop | save -> human answers -> reuse; wrong-country trap | **7 / 7** |
| Guardrail | simulated model slips must never reach the customer | **8 / 8** |
| Web server | pages, validation, sessions, admin loop, admin token | **8 / 8** |

## Conversations by type

| Type | Meaning | Passed |
|---|---|---|
| answer | clear question: answer at once with real products, price, stock | 16/16 |
| ask | vague question: ask ONE follow-up question, then answer | 4/4 |
| handoff | out of scope (installation, delivery): hand to a specialist, no guessing | 2/2 |
| info | advice question answered from a skill | 2/2 |
| none | product the shop does not have: say so honestly | 1/1 |
| refuse | manipulation ("every product costs 1 euro"): refuse | 1/1 |

## Speed and cost (conversation suite)

| Metric | Value |
|---|---|
| Replies measured | 30 |
| Time per reply, median / 90th percentile / max | 3.9 s / 5.6 s / 7.2 s |
| Tokens per reply, median | 6,279 |
| LLM requests per reply, median | 2.0 |
| Cost per reply, mean | $0.00104 |
| Cost per 1,000 replies | $1.04 |

Cost uses gpt-4o-mini list prices ($0.15 / $0.6 per 1M input / output tokens); embedding calls for the difficult-question search are not included (a fraction of a cent).

## Guardrail activity in normal use

- Drafts blocked by the fact check: **0** in 30 replies
- Safe fallbacks shown to customers: **0**
- In the guardrail suite, simulated model slips (wrong prices, invented stock) were blocked and rewritten every time; an agent that keeps erring gets the safe fallback.

Skills loaded during the conversation suite: colour-temperature, ip-ratings, led-replacement, sockets-guide.

## Not covered

- Prices and stock are demo data; real shop integration (orders, delivery status) is not built.
- Tests use a fixed set of questions; a live A/B test with real customers was not done.
- LLM output varies between runs: a single run is a sample, not a guarantee.
