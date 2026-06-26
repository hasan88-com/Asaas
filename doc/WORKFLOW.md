# WORKFLOW.md — Asaas (اثاثہ)

**Full end-to-end web application workflow.**
How a request flows through every layer: frontend → API → orchestrator → agent → tools → services → Supabase/data → back to the user. Pairs with TECH.md, AGENT_RULES.md, FLOW.md, DESIGN.md.

---

## 1. The layers (what talks to what)

```
┌───────────────────────────────────────────────────────────────┐
│  FRONTEND  (React + Vite + Tailwind)                          │
│  Chat page · dashboard · cards · guest mode                   │
└───────────────┬───────────────────────────────────────────────┘
                │  HTTPS + Supabase JWT (Authorization: Bearer)
                ▼
┌───────────────────────────────────────────────────────────────┐
│  API  (FastAPI)                                               │
│  verify JWT → authorize (ownership) → route to handler        │
└───────────────┬───────────────────────────────────────────────┘
                ▼
┌───────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR  (LangGraph StateGraph)                         │
│  load context → classify intent → route to role → assemble    │
└───────┬───────────────────────────────────────────────────────┘
        ▼                    ▼                      ▼
┌──────────────┐    ┌──────────────┐      ┌──────────────────┐
│  AGENT ROLE  │    │   TOOLS      │      │   LLM ROUTER     │
│ (profiler,   │───▶│ (suggest_… , │      │ Gemini/Groq/...  │
│  optimizer,  │    │  run_dcf, …) │      │ abstracted only  │
│  valuation…) │    └──────┬───────┘      └──────────────────┘
└──────────────┘           ▼
                   ┌──────────────────────────────────────────┐
                   │  SERVICES + DATA                          │
                   │  optimizer · valuation · technical ·      │
                   │  materiality · rate_impact · performance  │
                   │  adapters (yfinance, coingecko, sbp, …)   │
                   │  cache (Redis → DB → adapter)             │
                   └──────────────┬───────────────────────────┘
                                  ▼
                   ┌──────────────────────────────────────────┐
                   │  SUPABASE (Postgres) + Redis              │
                   │  RLS-protected tables; read-through cache │
                   └──────────────────────────────────────────┘
```

---

## 2. Opening the chat page (the screen you described)

**What the user sees on first open:**

```
                         اثاثہ
            Your Pakistan-focused wealth advisor

   ┌────────────────────────┐  ┌────────────────────────┐
   │ Suggest a portfolio    │  │ Value HBL for me       │
   │ for me                 │  │                        │
   └────────────────────────┘  └────────────────────────┘
   ┌────────────────────────┐  ┌────────────────────────┐
   │ Show RSI for OGDC      │  │ How does the SBP rate  │
   │                        │  │ affect my T-bills?     │
   └────────────────────────┘  └────────────────────────┘

   ┌──────────────────────────────────────────────┐
   │  Ask anything about your portfolio…      [↵]  │
   └──────────────────────────────────────────────┘
```

**Frontend behavior on load:**
1. `Chat.tsx` mounts → renders the empty state: wordmark (اثاثہ), tagline, and the four example chips (DESIGN.md §5c.3).
2. The chips are seeded prompts. Tapping one calls `sendMessage(text)` exactly as if typed.
3. No API call happens on load — the empty state is static until the user acts.

**The four example chips map to four different agents** — this is the demo of the whole system:
| Chip | Routes to | Tools called |
|---|---|---|
| "Suggest a portfolio for me" | Optimizer | suggest_portfolio, check_diversification |
| "Value HBL for me" | Valuation | extract_company_info, run_dcf, run_monte_carlo, run_multiples |
| "Show RSI for OGDC" | Technical | run_technical_analysis |
| "How does the SBP rate affect my T-bills?" | Rate-impact | analyze_rate_impact |

---

## 3. Full request trace (example: "Value HBL for me")

This is the complete path, layer by layer.

```
1. FRONTEND
   User taps chip → sendMessage("Value HBL for me")
   → append user bubble (optimistic, slide-up 200ms)
   → open SSE connection: POST /api/v1/chat
        headers: { Authorization: "Bearer <supabase_jwt>" }
        body: { message: "Value HBL for me" }
   → show streaming dots in a new agent bubble

2. API  (api/chat.py)
   → verify_supabase_jwt(token)  — signature, expiry, audience
   → get_current_user()          — resolve user_id
   → (RLS active on every DB call this user makes)
   → call orchestrator.process_message(user_id, message)  → returns SSE stream

3. ORCHESTRATOR  (agent/orchestrator.py — LangGraph)
   node: load_context  → fetch user's profile + holdings (SQLAlchemy, RLS)
   node: classify      → LLM (light model) classifies intent → "valuation", symbol "HBL"
   edge: route         → valuation node
   node: valuation     → run_valuation(symbol="HBL")

4. AGENT ROLE  (agent/roles/valuation.py)
   → call tool extract_company_info("HBL.KA")
   → call tool run_dcf("HBL.KA", assumptions)      (WACC uses SBP rate)
   → call tool run_monte_carlo("HBL.KA", ranges)   (returns distribution)
   → call tool run_multiples("HBL.KA", peers)
   → abstract results (symbol + metrics only, NO pii)
   → LLM (reasoning model) + valuation_prompt → plain-language explanation

5. TOOLS → SERVICES → DATA
   tools/run_dcf.py → services/valuation.py
     → cache.get_price("HBL.KA")  → Redis hit? return : DB? return : yfinance fetch
     → yfinance fundamentals (.KA)  — if thin, return "insufficient data" (no fabrication)
     → SBP rate from cache (for WACC)
     → compute, return NUMERIC dict

6. SUPABASE / REDIS
   reads: prices, instruments, risk_profiles, holdings  (all RLS-scoped to user_id)
   no writes (valuation is read-only)

7. BACK UP
   orchestrator assembles → SSE streams tokens to frontend
   → frontend replaces dots with streaming text
   → renders ValuationCard (Monte Carlo band hero) inline (DESIGN.md §5c.2)
   → disclaimer footer appended
```

---

## 4. The other three chips (same pattern, different role)

**"Suggest a portfolio for me"** → needs a profile first.
- classify → "optimize". load_context finds no confirmed profile → orchestrator routes to **profiler** first (asks the IPS questions), then optimizer. If profile exists → straight to optimizer → suggest_portfolio + check_diversification → OptimizerCard with donut + confirm action.

**"Show RSI for OGDC"** → technical.
- classify → "technical", symbol "OGDC". → run_technical_analysis on daily EOD from cache → TechnicalCard with RSI gauge.

**"How does the SBP rate affect my T-bills?"** → rate-impact.
- classify → "rate_impact". load_context finds user's T-bill holdings → analyze_rate_impact (inverse yield/price, SBP rate) → RateImpactCard with the dual-effect explanation.

---

## 5. Guest (no-login) variant

Same shape, fewer layers — no auth, no DB writes.
```
Frontend (GuestAnalyze.tsx)
  → user enters holdings (cookie counter checked)
  → POST /api/v1/portfolio/analyze-guest  (no JWT)
  → API checks cookie + per-IP Redis counter; if over limit → 429 → "sign up" prompt
  → optimizer service (analyze mode) on the entered holdings (live prices, real MPT)
  → returns analysis + diversified suggestion (held in browser, NOT persisted)
  → "Save it & track it" → register → replays into /portfolio/suggest
```

---

## 6. Why you might see "Something went wrong" on the chat page

That generic error means a layer in the chain above failed. Work down the list — these are the usual causes, most common first:

### A. Auth / JWT (most common)
- The frontend isn't sending the Supabase JWT, or it's expired/invalid → API returns 401.
- **Check:** browser DevTools → Network tab → the `/chat` request → is there an `Authorization: Bearer …` header? Is the response 401?
- **Fix:** ensure the Supabase session token is attached to the request; refresh the session if expired.

### B. Backend not running / wrong URL (very common in dev)
- Frontend calls the API at the wrong base URL, or the backend isn't running.
- **Check:** Network tab → is the request failing with "connection refused" / CORS error / 404?
- **Fix:** confirm the backend is running, the frontend's API base URL points to it, and CORS allows the frontend origin.

### C. Missing API key → LLM call fails
- Gemini/Groq key not set in backend `.env` → the orchestrator's LLM call throws → 500.
- **Check:** backend logs/terminal — look for an auth error from the LLM provider.
- **Fix:** set the LLM keys in the backend environment; restart.

### D. SSE not handled
- The endpoint streams Server-Sent Events but the frontend reads it as plain JSON (or vice versa) → parse error.
- **Check:** Network tab → response type of `/chat`; frontend console for a parse/stream error.
- **Fix:** frontend must consume the SSE stream (EventSource / fetch + ReadableStream), not `await res.json()`.

### E. Supabase connection / RLS
- DB connection string wrong, pooler not used, or an RLS policy blocks the query → 500.
- **Check:** backend logs for a DB connection or "permission denied for table" error.
- **Fix:** verify the Supabase pooler URL and that RLS policies allow the authenticated user's own rows.

### F. Orchestrator/tool exception
- A tool (e.g. yfinance for a thin PSX stock) throws instead of degrading gracefully → unhandled → 500.
- **Check:** backend logs for the stack trace; which tool/role failed.
- **Fix:** ensure every external call is wrapped (RULES.md A3.5) and degrades to a clear message, not an exception.

### The fastest diagnosis
Open browser **DevTools → Network**, send a chat message, click the `/chat` request:
- **No request at all** → frontend bug (button not wired / base URL empty).
- **401** → auth (A).
- **404 / connection refused / CORS** → backend not reachable (B).
- **500** → backend threw; read the **backend terminal logs** for the real error (C/E/F).
- **200 but UI errors** → SSE parsing (D).

The generic "Something went wrong" is the frontend's catch-all — the *real* error is in the Network tab response and the backend logs. Always look there first.

---

## 7. End-to-end integration checklist

Before the chat page works end to end, confirm each link:

- [ ] Backend running and reachable at the URL the frontend uses
- [ ] CORS allows the frontend origin
- [ ] Supabase session issues a JWT; frontend attaches it to every API call
- [ ] API verifies the JWT and resolves user_id
- [ ] RLS policies allow the user's own rows (not blocking legitimate reads)
- [ ] LLM keys (Gemini, Groq) set in backend env; llm_router reaches a provider
- [ ] Data keys (CoinGecko, FRED, Alpha Vantage) set; adapters return data
- [ ] `/chat` streams SSE; frontend consumes the stream (not `.json()`)
- [ ] Orchestrator routes the four example chips to the right roles
- [ ] Each role's tools degrade gracefully (no unhandled exceptions)
- [ ] Cards render the agent output (DESIGN.md §5c)

When all green, the four example chips each light up their respective agent end to end.

---

*End of WORKFLOW.md. The chain: chip → frontend → API (verify JWT) → orchestrator (classify+route) → role → tools → services → cache → Supabase → back as SSE → inline card. A failure in any link surfaces as "something went wrong" — diagnose via Network tab + backend logs.*
