# TECH.md — Asaas (اثاثہ)

**Technical Requirements & Database Schema**
Agentic wealth management platform · Pakistan market · MVP

> Companion to `PRD.md`. This document covers the technical stack, API surface, backend architecture, and the full database schema. The schema lives here because it is shaped directly by the tech and data-source decisions in this file.

---

## 1. Architecture overview

Asaas is a three-tier system: a data layer that ingests market and news data on a per-asset-class cadence, an agent/backend layer that reasons over that data and exposes a REST + streaming API, and a frontend that delivers chat, dashboard, and alerts.

```
Data sources ──▶ Ingestion workers ──▶ Supabase (Postgres) + Redis ──▶ FastAPI + Agent ──▶ React/Vite client
                                              ▲                      │
                                              └──── background jobs ─┘
```

**Core principle carried from the PRD:** autonomous analysis, human-approved decisions. The backend may compute, monitor, and recommend autonomously; it never executes a portfolio change without an explicit user-confirmed request.

---

## 2. Tech stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend framework | **FastAPI (Python 3.11+)** | Async, native OpenAPI, fits the Python data/ML ecosystem |
| Agent orchestration | **LangGraph** | Graph-based multi-agent orchestration — explicit nodes/edges for the role routing in AGENT_RULES.md §7 |
| Optimization | **PyPortfolioOpt** | Production-grade MPT; covariance, efficient frontier, max-Sharpe |
| Data — market | **yfinance** (stocks global + PSX `.KA`, commodities) | One adapter across three asset classes |
| Data — crypto | **CoinGecko** | Free, no auth, batched |
| Data — fixed income | **SBP scrape** (T-bills, policy rate) | Only authoritative source; event-driven |
| Data — macro | **FRED** | Macro context for agent reasoning |
| Data — backup | **Alpha Vantage** | Commodity gap-fill only (25 calls/day) |
| News | **PSX announcements, SBP press, Business Recorder, Dawn** | Scrape / RSS |
| Scraping | **Playwright** (JS pages) + **BeautifulSoup** (static) | PSX DPS fallback, news |
| Primary DB | **Supabase (managed PostgreSQL 15+)** | Hosted Postgres + built-in auth + Row-Level Security; free tier; schema unchanged from raw Postgres |
| DB access | **SQLAlchemy (async)** for domain data; Supabase client for auth glue only | Keep one ORM for portfolio/holdings/news; don't mix layers |
| Cache / queue | **Redis** | Hot price cache, rate-limit buffering, job broker |
| Background jobs | **Celery + Redis** (or APScheduler for simpler MVP) | Scheduled + event-driven monitoring |
| LLM — hard reasoning | **Gemini 2.5 Pro** | Highest free quality ceiling; rare complex tasks (~50 req/day) — same key as Flash |
| LLM — reasoning | **Gemini 2.5 Flash** | Large context for news + portfolio; routine reasoning |
| LLM — chat (fast) | **Groq · Llama 3.3 70B** | Lowest latency for conversation |
| LLM — chat (fast alt) | **Cerebras · Llama 3.3 70B** | Even higher throughput; Groq backup if rate-limited |
| LLM — light/high-volume | **Groq · Llama 3.1 8B instant** | Cheap fast calls; spares the 70B rate budget |
| LLM — reasoning alt | **Groq · Qwen3 32B / GPT-OSS 120B** | On-Groq reasoning option for materiality |
| LLM — fallback | **OpenRouter free slot** | Re-route on rate-limit |
| Frontend | **React + Vite + Tailwind + shadcn/ui** | Fast DX, component library, matches team stack |
| Charts | **Recharts / Chart.js** | Allocation pies, performance time-series |
| Auth | **Supabase Auth** issues JWT (login/session/refresh); **FastAPI verifies + owns authorization**; **RLS** backstops per-user isolation | Offload auth plumbing, keep ownership checks |
| Deploy | Render / Railway (free-tier friendly) | Low cost, simple CI |

---

## 3. Backend service structure

```
app/
├── main.py                  # FastAPI entry, router mount, middleware
├── core/
│   ├── config.py            # env, settings
│   ├── security.py          # verify Supabase JWT, authorization (ownership) checks
│   └── db.py                # async SQLAlchemy session, engine (via Supabase pooler)
├── models/                  # SQLAlchemy ORM (mirrors §7 schema)
├── schemas/                 # Pydantic request/response models
├── api/
│   ├── auth.py              # Supabase Auth integration + JWT verification
│   ├── profile.py           # risk profile CRUD
│   ├── portfolio.py         # suggest, confirm, get, reoptimize
│   ├── market.py            # prices, performance
│   ├── news.py              # feed, flags
│   └── chat.py              # agent chat (streaming)
├── agent/
│   ├── orchestrator.py      # LangGraph graph: intent → role routing
│   ├── tools/               # one module per tool (§5)
│   ├── llm_router.py        # provider selection + fallback
│   └── prompts/             # system prompts, abstraction rules
├── data/
│   ├── adapters/            # yfinance, coingecko, sbp, fred, alpha_vantage
│   ├── news/                # source scrapers + normalizer
│   └── cache.py             # Redis read-through helpers
├── services/
│   ├── optimizer.py         # PyPortfolioOpt wrapper, SBP risk-free
│   ├── materiality.py       # news → score → flag/log
│   ├── rate_impact.py       # SBP rate → T-bill yield/price
│   └── performance.py       # value calc, snapshots, drift
└── workers/
    ├── daily_eod.py         # stocks + commodities + snapshot
    ├── crypto_refresh.py    # batched coin prices
    ├── tbill_watch.py       # event-driven SBP scrape
    └── news_monitor.py      # ingest → match → score → flag
```

---

## 4. API surface

All endpoints are versioned under `/api/v1`. Auth via `Authorization: Bearer <jwt>`. Responses are JSON; chat is server-sent events (SSE).

### Auth
Auth is handled via **Supabase Auth** (login, session, refresh, password reset) which issues a JWT. The backend **verifies** that JWT and runs its own authorization checks; it does not store passwords.
| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/session` | Exchange/verify Supabase session; establish backend session |
| GET | `/auth/me` | Return current authenticated user (from verified JWT) |

> Registration, login, and refresh are performed against Supabase Auth (client-side SDK or via these proxy endpoints). The backend's job is to **verify** the Supabase-issued JWT on every request and enforce resource ownership — never to manage passwords itself.

### Profile
| Method | Path | Purpose |
|---|---|---|
| GET | `/profile` | Get risk profile |
| PUT | `/profile` | Create/update risk profile (risk, horizon, capital, constraints) |

### Portfolio
| Method | Path | Purpose |
|---|---|---|
| POST | `/portfolio/analyze-guest` | **No auth.** Analyze guest-entered holdings + return improved suggestion. Limited by browser cookie + per-IP Redis counter; persists nothing |
| POST | `/portfolio/suggest` | Run optimizer → return draft portfolio + rationale |
| POST | `/portfolio/confirm` | Lock actual holdings → state `confirmed` |
| GET | `/portfolio` | Get active portfolio + current value |
| GET | `/portfolio/holdings` | List holdings with live prices |
| POST | `/portfolio/reoptimize` | User-triggered; accepts optional `flag_id` reason |
| GET | `/portfolio/performance` | Time-series from snapshots + P&L |

### Market
| Method | Path | Purpose |
|---|---|---|
| GET | `/market/price/{symbol}` | Single asset price (read-through cache) |
| GET | `/market/search` | Search asset universe |
| GET | `/market/commodity-news/{symbol}` | On-demand commodity news |

### Analysis (on-demand, read-only)
| Method | Path | Purpose |
|---|---|---|
| GET | `/analysis/company/{symbol}` | Company info + fundamentals (yfinance) |
| POST | `/analysis/valuation/{symbol}` | DCF + Monte Carlo + multiples; degrades if data thin |
| GET | `/analysis/technical/{symbol}` | Technical indicators on daily EOD data |

### News & flags
| Method | Path | Purpose |
|---|---|---|
| GET | `/news/feed` | Personalized feed (matched to holdings) |
| GET | `/flags` | Pending material-event flags |
| POST | `/flags/{id}/dismiss` | Acknowledge / dismiss a flag |

### Chat
| Method | Path | Purpose |
|---|---|---|
| POST | `/chat` | Send message → SSE stream of agent response + tool results |
| GET | `/chat/history` | Retrieve conversation history |

### Guest mode (no-login analyze)

The `/portfolio/analyze-guest` endpoint powers the try-it flow (FLOW.md §2). Rules:

- **No auth, no persistence.** Accepts a list of holdings in the request body, runs the real optimizer (live prices, MPT, SBP risk-free), returns the analysis + improved suggestion. Writes nothing to the database.
- **Guest state lives client-side.** The frontend holds the guest's inputs and result in session state until/unless they register. On signup, the frontend replays the stored inputs into `/portfolio/suggest` so the result becomes the new account's draft portfolio.
- **Rate-limited** by two layers: a **browser cookie** tracking free-run count (soft, UX-facing) and a **per-IP Redis counter** (hard backstop, since cookies can be cleared). When the free limit is hit, the endpoint returns a `quota_exceeded` response and the UI prompts signup.
- **Cookie details:** on first guest run the server sets an HTTP-only cookie with an anonymous id + counter; each `analyze-guest` call increments it. The cookie is the normal-case limiter; the IP counter stops cookie-clearing / incognito abuse. Neither stores PII.
- **Price cache reused.** Guests mostly enter the same liquid KSE-100 names; the read-through price cache serves them without extra external calls.
- **No LLM PII concern** — guests provide no identity; the payload is symbols + amounts only, consistent with the abstraction rule (§5).

### External API quotas (enforced in `data/cache.py` + Redis counters)
| Source | Limit | Strategy |
|---|---|---|
| Gemini 2.5 Pro | ~2 RPM, ~50 req/day | Hard reasoning only; same key as Flash |
| Gemini 2.5 Flash | generous free tier (RPM/TPM) | Primary reasoning; abstracted payloads |
| Groq (all models) | free tier, rate-limited per model (~30 RPM, per-model RPD/TPM) | Chat + light + reasoning; one key, many models |
| Cerebras | free tier, rate-limited (high throughput) | Fast chat alternative to Groq |
| OpenRouter | free model slots | Fallback when a primary caps out |
| CoinGecko | ~10–50 calls/min | Batch all held coins, 30–60s cache |
| Alpha Vantage | 25 calls/day | Backup only, never in loops |
| FRED | Generous | Weekly refresh, cached |
| yfinance | Unofficial, no hard cap | Wrap in retry + fallback to PSX scrape |

> All LLM providers above are free (rate-limited, no token billing). Verify current model IDs and limits at the provider dashboards before locking them into `llm_router` — catalogs and quotas change.

### LLM routing (model structure)

`llm_router.py` selects a model per task, wired as LangGraph nodes. All routes are free-tier; the router falls through to OpenRouter on rate-limit.

| Task | Model | Provider | Why |
|---|---|---|---|
| User-facing chat | Llama 3.3 70B | Groq (or Cerebras) | Lowest latency; Cerebras as faster backup |
| Light / high-volume calls | Llama 3.1 8B instant | Groq | Cheap + fast; protects the 70B rate budget |
| Portfolio reasoning & rationale | Gemini 2.5 Flash | Gemini | Large context (news + holdings), good reasoning |
| Hard reasoning (rare) | Gemini 2.5 Pro | Gemini | Highest free quality ceiling for complex re-optimization / tricky judgment (~50/day) |
| News materiality scoring | Gemini 2.5 Flash *or* Qwen3 32B | Gemini / Groq | Reasoning quality; Qwen on Groq if Gemini budget tight |
| Rate-limit fallback (any task) | free model slot | OpenRouter | Keeps the agent responsive when a primary caps |

**Routing rules:**
- **Free-production providers only** — Gemini, Groq, Cerebras, OpenRouter.
- **Right-size the model** — never send a trivial call to the 70B, Flash, or Pro; route light tasks to Llama 8B, and reserve Gemini Pro for genuinely hard tasks (its ~50/day budget is small).
- **Abstracted payloads only** — every route obeys the no-PII-to-LLM rule (§5, §8).
- **Graceful fallthrough** — on rate-limit or failure, retry via OpenRouter (or Cerebras for chat) before surfacing an error.
- **One Groq key, many models** — chat, light, and reasoning-alt share the single free Groq key; mind the per-model rate limits.

---

## 5. Agent tools

The orchestrator exposes these as callable tools. The LLM selects tools based on conversation intent; results are normalized before returning.

| Tool | Service | Reads | Writes |
|---|---|---|---|
| `analyze_profile` | — | form input | `risk_profiles` |
| `suggest_portfolio` | optimizer | `risk_profiles`, `prices` | `portfolios` (draft), `holdings` |
| `check_diversification` | optimizer | `holdings` | — |
| `confirm_holdings` | — | user input | `portfolios` (confirmed), `holdings` |
| `track_value` | performance | `holdings`, `prices` | `portfolio_snapshots` |
| `fetch_relevant_news` | news | `holdings`, `news_items` | — |
| `assess_materiality` | materiality | `news_items`, `holdings` | `news_holding_link`, `flags` |
| `flag_event` | materiality | computed impact | `flags` |
| `analyze_rate_impact` | rate_impact | `news_items`, T-bill `holdings` | `flags` |
| `reoptimize` | optimizer | `portfolios`, `flags`, `prices` | `portfolios` (new draft) |
| `extract_company_info` | valuation | yfinance fundamentals | — |
| `run_dcf` | valuation | fundamentals, SBP rate (WACC) | — |
| `run_monte_carlo` | valuation | DCF inputs + assumption ranges | — |
| `run_multiples` | valuation | fundamentals, peer set | — |
| `run_technical_analysis` | technical | `prices` (daily EOD) | — |

> The valuation and technical tools are **read-only analysis** — they compute and return estimates, writing nothing. They run on user request only (not in any automatic flow). Valuation degrades gracefully when PSX fundamentals are thin and never fabricates missing financials.

**LLM data abstraction rule:** tools pass the LLM only abstracted data — asset symbol, weight, sector, computed metrics — never user identity, account numbers, or absolute balances. PII and money amounts stay in the backend.

---

## 6. Data flow & refresh orchestration

| Job | Trigger | Action |
|---|---|---|
| `daily_eod` | Cron, after market close | yfinance EOD (stocks + commodities) → update `prices` → write `portfolio_snapshots` |
| `crypto_refresh` | Interval + on dashboard load | CoinGecko batched → `prices` (cached 30–60s) |
| `tbill_watch` | New SBP announcement OR 3-month timer | Scrape SBP → update T-bill `prices` + `instruments` |
| `news_monitor` | Cron (daily / configurable) | Ingest → `news_items` → match to `holdings` → `assess_materiality` → `flags` or log |
| `rate_impact` | On SBP rate news detected | Recompute T-bill yield/price → `flags` if material |

Read path for prices is **read-through cache**: API checks Redis → on miss, reads `prices` table → on stale, triggers adapter fetch.

---

## 7. Database schema

Supabase (managed PostgreSQL). Design goals: third-normal-form for core entities, JSONB only where fields are genuinely variable (constraints, raw news payload), a single wide `prices` time-series table indexed for fast lookups, and immutable `portfolio_snapshots` for performance history. **Row-Level Security (RLS) is enabled on all user-owned tables** so a user can only access their own rows — a DB-level backstop to API authorization.

### 7.1 Entity relationships

```
users ──1:1── risk_profiles
  │
  └──1:N── portfolios ──1:N── holdings ──N:1── instruments
                │                                   │
                │                                   └──1:N── prices
                ├──1:N── portfolio_snapshots
                └──1:N── flags ──N:1── news_items
                                          │
              news_items ──N:M── instruments  (news_holding_link)
  │
users ──1:N── chat_messages
```

### 7.2 Tables

#### `users`
Mirrors Supabase Auth users; `id` matches the Supabase `auth.users` id. Passwords live in Supabase Auth, not here.
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | = Supabase `auth.users.id` |
| email | TEXT UNIQUE NOT NULL | from Supabase Auth |
| full_name | TEXT | |
| created_at | TIMESTAMPTZ DEFAULT now() | |
| updated_at | TIMESTAMPTZ | |

> No `password_hash` — Supabase Auth manages credentials. This table holds the app-side profile keyed to the auth user.

#### `risk_profiles` — 1:1 with users
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users(id) UNIQUE | one profile per user |
| risk_tolerance | TEXT | `conservative` / `moderate` / `aggressive` |
| horizon | TEXT | `short` / `medium` / `long` |
| investor_mode | TEXT | `long_term` / `active` |
| capital_pkr | NUMERIC(18,2) | investable capital |
| goal | TEXT | `growth` / `income` / `preservation` |
| constraints | JSONB | excluded sectors, crypto cap, liquidity needs |
| updated_at | TIMESTAMPTZ | |

#### `instruments` — the asset universe
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| symbol | TEXT UNIQUE NOT NULL | e.g. `HBL.KA`, `BTC`, `GC=F`, `TBILL-3M` |
| name | TEXT | display name |
| asset_class | TEXT NOT NULL | `psx_stock` / `global_stock` / `crypto` / `tbill` / `commodity` / `mutual_fund` |
| sector | TEXT | for diversification limits (PSX sectors) |
| currency | TEXT DEFAULT 'PKR' | native currency |
| data_source | TEXT | `yfinance` / `coingecko` / `sbp` / `fred` |
| metadata | JSONB | maturity (T-bills), coupon, exchange, etc. |
| is_active | BOOLEAN DEFAULT true | in tradable universe |

#### `prices` — time-series (single wide table)
| Field | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| instrument_id | UUID FK → instruments(id) | |
| price | NUMERIC(18,6) NOT NULL | close / current |
| price_date | DATE NOT NULL | EOD date |
| open / high / low | NUMERIC(18,6) | OHLC where available |
| volume | BIGINT | |
| source | TEXT | provenance |
| fetched_at | TIMESTAMPTZ DEFAULT now() | freshness check |

**Indexes:** `UNIQUE(instrument_id, price_date)`; `INDEX(instrument_id, price_date DESC)` for latest-price lookups.

#### `portfolios`
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users(id) | |
| name | TEXT | |
| status | TEXT NOT NULL | `draft` / `confirmed` / `tracked` |
| expected_return | NUMERIC(8,4) | from optimizer |
| expected_risk | NUMERIC(8,4) | volatility |
| sharpe | NUMERIC(8,4) | with SBP risk-free |
| risk_free_rate | NUMERIC(6,4) | SBP policy rate snapshot at optimization |
| rationale | TEXT | agent's plain-language explanation |
| created_at | TIMESTAMPTZ DEFAULT now() | |
| confirmed_at | TIMESTAMPTZ | when user activated |

#### `holdings` — positions within a portfolio
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| portfolio_id | UUID FK → portfolios(id) | |
| instrument_id | UUID FK → instruments(id) | |
| target_weight | NUMERIC(6,4) | optimizer's suggested weight |
| actual_weight | NUMERIC(6,4) | confirmed weight (may differ) |
| quantity | NUMERIC(18,6) | units held |
| entry_price | NUMERIC(18,6) | cost basis |
| entry_date | DATE | |

**Index:** `UNIQUE(portfolio_id, instrument_id)`.

#### `portfolio_snapshots` — immutable daily value history (powers performance chart)
| Field | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| portfolio_id | UUID FK → portfolios(id) | |
| snapshot_date | DATE NOT NULL | |
| total_value_pkr | NUMERIC(18,2) | computed from holdings × prices |
| pnl_absolute | NUMERIC(18,2) | vs. cost basis |
| pnl_percent | NUMERIC(8,4) | |
| breakdown | JSONB | per-asset-class value split |

**Index:** `UNIQUE(portfolio_id, snapshot_date)`.

#### `news_items`
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| source | TEXT NOT NULL | `psx` / `sbp` / `business_recorder` / `dawn` |
| headline | TEXT NOT NULL | |
| url | TEXT | |
| published_at | TIMESTAMPTZ | |
| level | TEXT | `direct` / `sector` / `macro` |
| sentiment | TEXT | `positive` / `negative` / `neutral` |
| materiality_score | NUMERIC(4,3) | 0–1 |
| summary | TEXT | agent's short impact note |
| raw | JSONB | original scraped payload |
| ingested_at | TIMESTAMPTZ DEFAULT now() | |

#### `news_holding_link` — N:M news ↔ instruments
| Field | Type | Notes |
|---|---|---|
| news_id | UUID FK → news_items(id) | composite PK |
| instrument_id | UUID FK → instruments(id) | composite PK |
| relevance | NUMERIC(4,3) | match strength |

#### `flags` — pending material events awaiting user decision
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| portfolio_id | UUID FK → portfolios(id) | |
| news_id | UUID FK → news_items(id) NULL | source event (nullable for drift/rate flags) |
| type | TEXT | `news` / `rate_impact` / `drift` |
| severity | TEXT | `high` / `medium` |
| message | TEXT | impact rationale shown to user |
| status | TEXT DEFAULT 'pending' | `pending` / `acknowledged` / `actioned` |
| created_at | TIMESTAMPTZ DEFAULT now() | |
| resolved_at | TIMESTAMPTZ | |

#### `chat_messages`
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users(id) | |
| role | TEXT | `user` / `assistant` |
| content | TEXT | |
| tool_calls | JSONB | tools invoked + results (audit) |
| created_at | TIMESTAMPTZ DEFAULT now() | |

### 7.3 Storage decisions

- **One `prices` table, not per-class tables.** Asset class lives on `instruments`; prices stay uniform. Simpler queries, one index strategy. Partition by `price_date` later if volume grows.
- **JSONB only for variable fields** — `constraints`, `metadata`, `breakdown`, `raw`, `tool_calls`. Everything queried/filtered is a real column.
- **Snapshots are immutable** — never updated, only inserted daily. This is the audit trail and the performance chart source.
- **Weights stored as decimals** (0.0–1.0), formatted to percentages in the UI.
- **Money as `NUMERIC`, never float** — no floating-point drift on currency.
- **Soft references for nullable events** — `flags.news_id` is nullable so drift and rate-impact flags (which have no news item) fit the same table.

---

## 8. Security & privacy

- **Auth via Supabase Auth** — issues JWTs; backend verifies the JWT on every request and enforces resource ownership. No passwords stored app-side.
- **Row-Level Security (RLS)** enabled on all user-owned tables — a user can only read/write their own rows, enforced at the database, backstopping API authorization. Three layers: Supabase Auth (identity) → FastAPI (authorization) → RLS (DB isolation).
- **Connection pooling** — use Supabase's PgBouncer pooler for async FastAPI + background workers to stay within free-tier connection limits.
- **No financial PII to LLMs.** The agent abstraction layer (§5) strips identity and absolute amounts before any LLM call; the model sees symbols, weights, and metrics only.
- All external secrets (API keys) in environment variables, never in code or the repo.
- Rate-limit counters in Redis prevent free-tier quota breaches and accidental key exposure via overuse.
- HTTPS only; CORS locked to the known frontend origin.

---

## 9. Open technical decisions

| Decision | Options | Lean |
|---|---|---|
| T-bill valuation | Proper DCF pricing vs. simplified directional | Simplified for MVP, DCF as upgrade |
| Job runner | Celery+Redis vs. APScheduler | APScheduler for MVP simplicity |
| Multi-portfolio | Single vs. multiple per user | Single for MVP (schema already supports N) |
| Local gold price | International only vs. local PKR scrape | Convert via PKR/USD FX for MVP |

> The schema already supports multiple portfolios per user (`portfolios.user_id` is 1:N), so enabling multi-portfolio later is a UI/API change, not a migration.

---

*End of TECH.md — pairs with PRD.md. Next: RULES.md (execution plan + AI-coder guardrails).*
