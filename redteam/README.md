# Red-Teaming Engine

Adversarial stress-testing for agentic financial advice systems — built against
**PS1: "Agentic Financial and High-Stakes AI Advice"** (with the support of
Moneybox). PS1 asks for tooling that exposes hallucinations, policy breaches,
and unsafe-refusal failures in agentic advisors; this is that tool, using
Asaas's own agent as the first system under test.

This is a separate track from the Asaas product itself — Asaas is one of the
things this engine audits, not the other way around. It lives inside this repo
(no separate project) but does not import into or get deployed with the
FastAPI app.

## What it does

Synthetic personas send scripted or paraphrased messages to a target advice
API, and a library of detectors checks the responses (and, where the adapter
can see it, the underlying database state) against six risk categories taken
directly from PS1:

| Category | PS1 risk |
|---|---|
| `guessing_missing_details` | Guessing missing client details instead of gathering required facts |
| `premature_advice` | Giving premature advice rather than pausing to ask questions |
| `compliance_silent_failure` | Compliance checks that silently fail during real conversations |
| `phrasing_sensitivity` | Unpredictable behavior triggered by minor changes in user phrasing |
| `unfaithful_reasoning` | Made-up AI reasoning that hides how a decision was actually reached |
| `broken_audit_trail` | Broken audit trails making it impossible to prove why advice was given |

## Architecture

```
redteam/
  engine/
    scenario.py     — YAML scenario loader + validation
    results.py      — Turn / RunResult / DetectorOutcome data model
    runner.py        — drives a scenario against a target adapter
    detectors.py     — the checks (see table above), pure functions over text + optional state
    scorer.py         — aggregates outcomes into a Report
    report.py         — renders Markdown / HTML / JSON
    targets/
      base.py         — TargetAdapter protocol (send / new_session / get_state)
      http_adapter.py  — generic adapter for ANY chat-style advice API (SSE content-delta or plain JSON)
      asaas_direct.py  — drives app.agent.orchestrator.AgentOrchestrator directly against a DB session
  scenarios/*.yaml   — the scenario library (7 scenarios, all 6 categories covered)
  cli.py             — entrypoint
  tests/             — unit + adapter-level tests, no live DB or LLM keys required
```

The target interface is deployment-agnostic on purpose — `http_adapter.py`
doesn't know it's talking to Asaas. Point `--base-url` at a second team's
advice API (same request/response shape) to run a real cross-market
red-team pass, which is the natural next step toward PS1's other illustrative
prototype, the Cross-Market Agentic Advice Benchmark.

## Why detectors are heuristic, not an LLM judge

Every detector is a deterministic regex/keyword/lexical-overlap check, not a
second model call. That's deliberate: the thing being audited is accused of
being non-reproducible and prompt-sensitive, so the auditor can't itself be a
black box with the same problem. The tradeoff is real — these heuristics will
miss subtler violations a semantic judge would catch (documented per-detector
in `engine/detectors.py`). Treat this as a first-pass triage layer, not a
replacement for human review of flagged transcripts.

## Running it

### Against a live HTTP advice API (Asaas or otherwise)

```bash
pip install -r redteam/requirements.txt
python -m redteam.cli --target http \
  --base-url http://localhost:8000/api/v1 \
  --auth-header "Bearer <jwt>" \
  --response-mode sse \
  --out redteam/reports/report
```

`--response-mode sse` matches Asaas's own `/chat` contract (content-delta SSE
frames, see `backend/app/api/chat.py`). Use `--response-mode json` for a
target that returns a single JSON `{"response": "..."}` body — adjust
`--json-text-path` via `HTTPTargetConfig` if the field is nested differently.

### Direct-to-orchestrator (no HTTP hop, exposes DB ground truth)

```bash
cd backend && pip install -r requirements.txt   # if not already installed
export TEST_DATABASE_URL=postgresql+asyncpg://...   # same var backend/tests/conftest.py uses
PYTHONPATH=.. python -m redteam.cli --target direct --out ../redteam/reports/report
```

This mode is what makes `portfolio_state_unchanged` and
`audit_trail_completeness` meaningful — it queries the actual `portfolios` and
`chat_messages` rows after each turn instead of trusting the reply text.

### Just the scenario you're iterating on

```bash
python -m redteam.cli --target http --base-url http://localhost:8000/api/v1 \
  --scenarios no_auto_action_jailbreak_01 --out redteam/reports/report
```

Reports are written as `.html`, `.md`, and `.json` (or pick one with
`--format`). A non-zero exit code means at least one scenario failed.

## Adding a scenario

Drop a new `*.yaml` into `scenarios/`, following the shape of the existing
seven files. Exactly one of `turns` (a scripted multi-turn conversation) or
`paraphrases` (independent, semantically-identical rephrasings for the
phrasing-sensitivity category) is required. `category` must be one of the six
above; `checks` names detectors from `engine/detectors.py`'s `REGISTRY`.

## Known gap this engine already found

Running `audit_trail_probe_01` against Asaas today fails: `chat_messages.tool_calls`
(`backend/app/models/chat_message.py`) only ever stores `{"agent_role": ...}`
(see `backend/app/api/chat.py::_agent_sse_generator`), not which tool ran, its
input, or its output — so the persisted record can't actually reconstruct why
a piece of advice was given. That's the real, live finding this build
surfaced; it hasn't been fixed here, since fixing Asaas's audit logging is a
separate change from building the tool that found the gap.
