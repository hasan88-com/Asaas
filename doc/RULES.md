# RULES.md — Asaas (اثاثہ)

**Execution plan + guardrails for AI coders and contributors**
Read this before writing any code. Pairs with `PRD.md` and `TECH.md`.

> This file is authoritative. When `PRD.md`, `TECH.md`, and this file agree, follow them. If a request conflicts with these rules, stop and surface the conflict — do not silently improvise an alternative.

> **Two rule files, two audiences.** This file (`RULES.md`) governs the engineers and AI coders *building* Asaas. `AGENT_RULES.md` governs how the agents *inside* Asaas behave at runtime (per-role conduct). When implementing agent roles, follow both.

---

## PART A — RULES (read first, always apply)

### A1. Non-negotiable product rules

These come from the PRD and must never be violated, regardless of what a prompt asks:

1. **The agent suggests; the user decides.** Never auto-execute a portfolio change, rebalance, or trade. Every change requires an explicit user-confirmed API call. No "helpful" automation around this.
2. **No financial PII to LLMs.** Strip user identity, account numbers, and absolute money amounts before any LLM call. The model sees symbols, weights, sectors, and computed metrics only. This is enforced in the agent abstraction layer — do not bypass it.
3. **One agent, many users.** Do not create per-user agent instances. The agent is stateless; all user state lives in the database, loaded per request by `user_id`.
4. **SBP policy rate is the risk-free rate** in all optimization. Never default to 0% or a US rate.
5. **Crypto is a supported, legal asset class.** Do not add "regulatory risk" warnings or treat it as special. Cap exposure via normal risk constraints only.
6. **yfinance is primary for stocks (global + PSX `.KA`) and commodities.** PSX scraping is a fallback only — for freshness checks, missing tickers, and dividends. Do not build a scrape-first stock pipeline.

### A2. Stick-to-the-plan rules

1. **Do not change the stack.** Use what `TECH.md` §2 specifies. Do not introduce a new framework, database, ORM, or library without it being added to TECH.md first.
2. **Do not invent schema.** Tables, fields, and types are defined in `TECH.md` §7. If you need a new field or table, propose it as a schema change to TECH.md before writing migration code — do not add ad-hoc columns.
3. **Do not redesign the API.** Endpoints are in `TECH.md` §4. Match paths, methods, and versioning exactly.
4. **Respect external quotas.** The limits in `TECH.md` §4 are hard. Never put Alpha Vantage in a loop (25/day). Always batch CoinGecko. Always cache. Wrap yfinance in retry + fallback.
5. **No browser storage in any frontend artifact.** Use React state. (localStorage/sessionStorage are unsupported in the target render environment.)
6. **Money is `NUMERIC`, never float.** No floating-point currency anywhere — DB, Python, or JS.
7. **Guest mode persists nothing.** The `/portfolio/analyze-guest` path must not write to the database. Guest inputs and results live in client session state until the user registers, at which point they replay into the normal `/portfolio/suggest` flow. Limit guest usage with a **browser cookie** (free-run counter) backed by a **per-IP Redis counter** (hard backstop — cookies can be cleared); on limit, return `quota_exceeded` and prompt signup. The cookie stores an anonymous id + counter only, never PII. (See TECH.md guest mode, FLOW.md §2.)
8. **Keep `BUILD_LOG.md` current.** After creating, editing, or deleting any file, update `BUILD_LOG.md` in the same change — record what the file is, what it does, and what changed. This file is the single source of truth for the build's current state; never let it fall out of sync. Treat a change as incomplete until the log is updated. (Format defined in `BUILD_LOG.md` itself.)

### A3. Code quality rules

1. **Async throughout the backend.** FastAPI + async DB sessions. No blocking calls in request handlers — push slow work (scrapes, LLM calls) to background tasks or await properly.
2. **One responsibility per module.** Follow the structure in `TECH.md` §3. Adapters don't optimize; the optimizer doesn't scrape; tools don't talk to the DB directly except through services.
3. **Pydantic at the boundary.** All request/response bodies validated by Pydantic schemas. No raw dicts crossing the API edge.
4. **Read-through cache for prices.** Always: Redis → DB → adapter. Never hit an external source directly from a request handler.
5. **Every external call wrapped.** try/except with a defined fallback (cached value, alternate source, or graceful error). External sources fail — handle it.
6. **Secrets in env only.** No API keys, tokens, or credentials in code, config files, or the repo. Ever.
7. **Disclaimers on advice.** Any portfolio suggestion surfaced to the user carries the "suggested allocation, not financial advice" framing.

### A4. When to stop and ask

Stop and surface the issue (do not guess) when:
- A request conflicts with any rule in A1.
- A task requires a schema, stack, or API change not yet in the docs.
- A data source is unavailable and no fallback is defined.
- The materiality or optimization logic would need a financial assumption not specified in the docs.

---

## PART B — IMPLEMENTATION PLAN

Build in phases. Each phase has a milestone (a working, testable state). Do not start a phase before the previous milestone passes its tests. Security (Part C) applies in every phase — run SAST + SCA in CI from Phase 0, DAST per milestone, and a manual penetration pass before any public release.

### Phase 0 — Foundation
**Goal:** project skeleton runs, DB connects, auth works.

- Repo + project setup; FastAPI app boots
- Supabase (Postgres) + Redis connected via pooler; migrations framework in place
- Implement schema from `TECH.md` §7 (all tables, indexes, relations); enable RLS on user-owned tables
- Auth: Supabase Auth integration + backend JWT verification + ownership checks
- Health-check endpoint

**Milestone 0:** a user can register, log in, and hit an authenticated endpoint. Schema matches TECH.md exactly.

### Phase 1 — Data layer
**Goal:** market data flows into the DB and is queryable.

- Adapters: yfinance (global + `.KA`), CoinGecko, SBP scrape, FRED, Alpha Vantage (backup)
- Read-through price cache (Redis → DB → adapter)
- `instruments` seeded with the liquid KSE-100 subset + chosen crypto + T-bills + commodities
- `daily_eod` and `crypto_refresh` workers
- Market endpoints (`/market/price`, `/market/search`)

**Milestone 1:** prices for the full MVP universe are fetched, cached, and served via the API. Quotas respected (verify Alpha Vantage stays under 25/day in testing).

### Phase 2 — Portfolio engine
**Goal:** the optimizer produces a real, diversified portfolio.

- `optimizer.py`: PyPortfolioOpt wrapper, SBP rate as risk-free, sector concentration limits
- Profile endpoints + `analyze_profile`
- `/portfolio/suggest` → draft portfolio + rationale
- `/portfolio/confirm` → confirmed holdings, state transition
- `performance.py` + `portfolio_snapshots`; `/portfolio/performance`

**Milestone 2:** a profiled user receives a suggested portfolio with allocation, expected return/risk, Sharpe (local risk-free), and a rationale; can confirm it; sees performance over time.

### Phase 3 — Agent & chat
**Goal:** conversational agent with tool use and provider routing.

- `orchestrator.py` (LangGraph) + `llm_router.py` (task-based routing per TECH.md §4: Gemini Flash reasoning + Pro for hard tasks, Groq/Cerebras chat, Groq light, OpenRouter fallback)
- Agent tools from `TECH.md` §5
- Abstraction layer (A1.2) — verify no PII leaves to LLMs
- `/chat` SSE streaming + history

**Milestone 3:** a user can ask "build me a portfolio" or "how is my portfolio doing?" in chat and get a correct, personalized, tool-backed answer. PII abstraction verified.

### Phase 4 — News & monitoring
**Goal:** the continuous monitoring loop flags material events.

- News scrapers + normalizer (`news_items`)
- `materiality.py`: match to holdings → score → flag/log
- `rate_impact.py`: SBP rate → T-bill yield/price
- `news_monitor` worker (per-user loop), drift detection
- `/news/feed`, `/flags`, `/portfolio/reoptimize` (accepts flag reason)

**Milestone 4:** an SBP rate event or earnings item is ingested, matched to a user's holdings, scored, and surfaced as a flag with rationale; user can trigger re-optimization referencing that flag.

### Phase 5 — Frontend
**Goal:** the UI ties it together.

- React + Vite + Tailwind + shadcn/ui
- Onboarding form → suggestion view (allocation chart)
- Confirm flow; portfolio dashboard (value, P&L, time-series)
- Personalized news feed + flag alerts
- Chat interface (streaming)

**Milestone 5:** the full reference walkthrough works end to end in the UI: form → suggestion → confirm → flag → re-optimize.

---

## PART C — SECURITY

Security is not a final phase — it is applied throughout and verified before each milestone. Application security testing (AST) identifies vulnerabilities before they reach production. Build with the OWASP Top 10 in mind from Phase 0.

### C1. Security rules (apply while coding)

1. **Input validation everywhere.** Validate and sanitize all input at the Pydantic boundary. Never trust client data. This is the primary defense against injection and XSS.
2. **Parameterized queries only.** Use the ORM or parameterized statements for every DB call. Never build SQL by string concatenation — this prevents SQL injection.
3. **Output encoding.** Escape/encode any user-derived data rendered in the frontend to prevent cross-site scripting (XSS).
4. **Authentication hardening.** Supabase Auth handles credentials, sessions, and refresh — configure strong password policy and rate-limited login there. The backend verifies the Supabase JWT on every request (check signature, expiry, audience) and tests session handling. No passwords stored app-side.
5. **Authorization on every endpoint.** Verify the authenticated user owns the resource (`user_id` match) before returning or mutating it. No user may read or change another user's profile, portfolio, holdings, flags, or chat. Auth is via Supabase Auth (issues JWT); the backend verifies it and owns authorization. **Enable Row-Level Security (RLS)** on all user-owned tables as a DB-level backstop. This is the most likely real bug — test it explicitly.
6. **Encryption in transit and at rest.** HTTPS/TLS for all traffic; sensitive fields encrypted at rest. Verify TLS is configured correctly (no downgrade, valid cert).
7. **No security misconfiguration.** No default credentials, no debug mode in production, no open cloud storage, no verbose error stack traces returned to clients, CORS locked to the known frontend origin.
8. **Dependency hygiene.** Run Software Composition Analysis (SCA) on all third-party/open-source packages; patch known-vulnerable dependencies before release.
9. **Secrets never in code or repo** (restated from A3.6 — it is also a security gate).

### C2. Security testing methods

Run these against the app as part of the test process. Follow the standard flow: **plan scope → scan → attempt exploit → report with remediation.**

| Method | What it does | When | Suggested tool |
|---|---|---|---|
| **SAST** (static) | Analyzes source code for vulnerabilities without running it ("white box") — injection, hardcoded secrets, unsafe patterns | Every commit / CI | SonarQube |
| **DAST** (dynamic) | Scans the running app for SQL injection, XSS, and other runtime flaws ("black box") | Per milestone, on a deployed test build | OWASP ZAP |
| **SCA** (composition) | Flags vulnerabilities in open-source dependencies | Every dependency change / CI | Snyk |
| **Penetration testing** | Manual expert attempt to exploit logic flaws automated scans miss — especially authorization bypass | Before any public release | manual + Burp Suite / OWASP ZAP |
| **Vulnerability scanning** | Automated check for known CVEs in app + infrastructure | Scheduled | OWASP ZAP / scanner of choice |

### C3. OWASP-aligned security checklist (must pass before public release)

1. **Injection** — SQL/command/LDAP injection blocked (parameterized queries, validated input).
2. **Broken authentication** — weak-password rejection, session management, brute-force resistance verified.
3. **Broken authorization** — automated test confirms no cross-user data access on any endpoint; RLS enabled on all user-owned tables as a DB-level backstop.
4. **Sensitive data exposure** — TLS configured correctly; no secrets or PII in responses, logs, or errors.
5. **XSS** — all user-derived output encoded; DAST scan clean.
6. **Security misconfiguration** — no debug mode, no default creds, no stack traces to client, CORS locked.
7. **Vulnerable components** — SCA scan clean; no known-vulnerable dependencies shipped.
8. **PII-to-LLM** — restated security gate: confirm no identity/amount leaves to any model (ties to A1.2).

> Note: the no-auto-action rule (A1.1) is also a security concern — an authorization or logic flaw that lets a portfolio change occur without explicit user action is a critical-severity bug. Test for its absence under adversarial input, not just normal flow.

---

## PART D — TESTING (functional)

### D1. Methods by layer

| Layer | Method | Tool |
|---|---|---|
| Adapters / services | Unit tests with mocked external calls | pytest |
| API endpoints | Integration tests against a test DB | pytest + httpx |
| Optimizer | Property/sanity tests (weights sum to 1, no negative weights, sector caps respected) | pytest |
| Materiality | Fixture-based: known news → expected flag/no-flag | pytest |
| Agent tools | Tool-level tests + abstraction assertion (no PII in LLM payloads) | pytest |
| Frontend | Component + key-flow E2E | Vitest + Playwright |

### D2. Mandatory test gates (must pass before a milestone is "done")

1. **Schema integrity** — DB matches TECH.md; all FKs and unique constraints present.
2. **Quota safety** — a full daily cycle in tests stays within every external limit.
3. **Optimizer validity** — output weights are valid (sum to 1, within bounds, sector caps honored, uses SBP risk-free).
4. **PII abstraction** — automated assertion that no LLM payload contains user id, email, account number, or absolute PKR amount.
5. **No-auto-action** — there is no code path that mutates a confirmed portfolio without an explicit user-initiated request. Test for its absence.
6. **Money type** — no float used for any currency value (lint/grep check).

### D3. Test data

- Use synthetic users and a fixed seed universe for all tests.
- Never use real user PII in tests or fixtures.
- For news/materiality tests, keep a fixtures file of real-shaped (but static) news items so scoring is reproducible.

---

## PART E — DEFINITION OF DONE (per task)

A task is done only when:
1. It follows every applicable rule in Part A.
2. It matches the spec in PRD.md / TECH.md (no undocumented deviations).
3. Tests for the relevant gates in Part C (security) and Part D (functional) pass.
4. No secrets, no float-money, no PII-to-LLM, no auto-action introduced; no injection, XSS, or cross-user access path introduced.
5. The milestone's working state is demonstrable.
6. `BUILD_LOG.md` is updated to reflect any file created, edited, or deleted in the task.

---

*End of RULES.md. If anything here is ambiguous, ask before coding — a clarifying question is always cheaper than an off-plan implementation.*
