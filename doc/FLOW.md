# FLOW.md — Asaas (اثاثہ)

**User flows — screen by screen**
Pairs with `PRD.md`, `TECH.md`, `RULES.md`, `DESIGN.md`. This file maps what the *user* sees and does, screen to screen. (The PRD flowcharts show how the *system* reasons; this shows the human's path through the product.)

---

## 1. Flow map (overview)

```
                    ┌─────────────┐
                    │   Landing   │
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌────────────┐    ┌──────────┐    ┌──────────┐
   │ Try it     │    │ Register │    │  Log in  │
   │ (no login) │    └────┬─────┘    └────┬─────┘
   └─────┬──────┘         │               │
         ▼                ▼               │
  ┌─────────────┐  ┌─────────────┐        │
  │ Enter your  │  │ Onboarding  │        │
  │ holdings    │  │   form      │        │
  └──────┬──────┘  └──────┬──────┘        │
         ▼                ▼               │
  ┌─────────────┐  ┌─────────────┐        │
  │  Analysis + │  │  Suggested  │        │
  │  improved   │  │  portfolio  │        │
  │  suggestion │  └──────┬──────┘        │
  └──────┬──────┘         ▼               │
         │         ┌─────────────┐        │
         │         │  Confirm    │        │
   "Save it?"      │  holdings   │        │
         │         └──────┬──────┘        │
         ▼                └───────┬───────┘
   ┌──────────┐                   ▼
   │ Register │────────────▶┌─────────────┐
   │(carries  │             │  Dashboard  │◀────────┐
   │ result)  │             │  (home)     │         │
   └──────────┘             └──┬───┬───┬──┘         │
                     ┌─────────┘   │   └────────┐   │
                     ▼             ▼            ▼   │
                ┌─────────┐ ┌─────────┐ ┌─────────┐ │
                │  Chat   │ │  News   │ │  Flags  │ │
                └─────────┘ └─────────┘ └────┬────┘ │
                                             ▼      │
                                       ┌──────────┐ │
                                       │Re-optimize│─┘
                                       └──────────┘
```

Three entry points. A **guest** can "Try it" with no login — enter holdings they already own, get a real analysis + improved suggestion, then optionally register to save it. A **new user** registers and goes through full onboarding. A **returning user** logs in straight to the dashboard.



---

## 2. Guest "try it" flow (no login)

A first-time visitor can experience the core value — a real portfolio analysis — before creating an account. The hook is **analyze mode**: the guest enters holdings they already own, and the agent shows what's wrong and how to improve it. This meets people where they are and creates the "it sees a problem I didn't" moment that drives signup.

```
Landing → "Try it, no signup"
   │
   ▼
Enter your holdings (what you already own)
   - add instruments + rough amounts
   │
   ▼
Real analysis runs (live prices, real MPT)
   - diversification, concentration, risk
   - an improved, more diversified suggestion
   │
   ▼
"Save it & track it" → Register (carries the result)
   │                          │
   │                          ▼
   └─ or leave            account created → result becomes draft → Confirm → Dashboard
```

### Step G1 — Enter holdings
**Screen:** "What do you own right now?" The guest adds instruments (search the universe) and rough amounts or weights. No identity asked.
**User does:** lists their current holdings.
**System:** holds input in **browser/session state only** — nothing written to the database.

### Step G2 — Analysis + improved suggestion
**Screen:** a real, computed analysis of what they entered:
- **Current allocation** donut + concentration read ("70% in banking").
- **Risk metrics** on their current mix (volatility, diversification).
- **An improved portfolio** — the optimizer's more-diversified version, side by side.
- Plain-language: what's concentrated, what the improvement changes, why.
- "Suggested allocation, not financial advice" disclaimer.

**User does:** sees the value immediately. Can tweak inputs and re-run.
**System:** runs the **real optimizer** (live prices, MPT, SBP risk-free) — result is genuine, just not persisted.
**Guardrails:** guest usage is limited by a **browser cookie** (tracks free runs) backed by **server-side IP rate-limiting** (the real protection, since cookies can be cleared); price data cached (guests mostly enter the same liquid KSE-100 names) — see TECH.md.

### Guest usage limit (cookie + IP)
- On first guest run, the site sets a **cookie** holding an anonymous identifier + a run counter.
- Each guest analysis increments the counter.
- After the free limit is reached, the guest is **blocked from further runs and prompted to sign up** ("You've used your free analyses — create an account to keep going and save your portfolio").
- Because cookies can be cleared / dodged via incognito, the cookie is the **soft** limiter; a **per-IP server-side counter (Redis)** is the hard backstop against abuse.
- Signing up removes the limit — the account flow takes over.

### Step G3 — Convert to account
**Screen:** "Like what you see? Create an account to save this and track it over time."
**User does:** registers (or leaves — no pressure, no email asked just to view).
**System on signup:** the guest's session-held inputs + result are replayed into the normal flow → become the new account's **draft portfolio** → user proceeds to Confirm holdings → Dashboard. No orphaned guest records; the DB is only touched once they commit.

### Guest scope (deliberately limited)
The guest flow exposes **only** the analyze → suggest moment. Chat, news, flags, and monitoring require an account (they need persistence). The demo sells the *result*; the account delivers the *ongoing relationship*.

| Guest can | Guest cannot |
|---|---|
| Enter current holdings | Save a portfolio |
| See real analysis + suggestion | Access chat / news / flags |
| Tweak inputs and re-run | Be monitored over time |
| Convert to an account anytime | Persist anything server-side |

---

## 3. First-time user flow (the core journey)

This is the primary path and the one to build first. It maps directly to the three agent phases (PRD §4): onboarding → activation → monitoring.

### Step 1 — Register
**Screen:** email, password, name.
**User does:** creates an account.
**System:** creates `users` row, issues JWT, routes to onboarding.
**Next:** Onboarding form.

### Step 2 — Onboarding questionnaire (Phase 1 begins)
**Screen:** a short, friendly questionnaire structured on **Investment Policy Statement (IPS)** components — the professional framework for defining an investor. One question group per view (not a wall of fields).

1. **Return objective** — "What are you aiming for?" → grow wealth / generate income / beat inflation.
2. **Risk — willingness** — "If your portfolio dropped 20% in a month, what would you do?" → sell (conservative) / hold (moderate) / buy more (aggressive). *(Behavioral question — more reliable than self-labeling.)*
3. **Risk — ability** — "Could you handle a loss without affecting your living needs?" → captures capacity to take risk vs. desire. **Profile to the lower of willingness and ability.**
4. **Time horizon** — "When will you need this money?" → <1yr / 1–3yr / 3+yr.
5. **Capital** — "How much are you investing?" (PKR).
6. **Liquidity needs** — "How much quick access to cash do you need?" → emergency buffer / upcoming expenses.
7. **Tax considerations** — "Any tax situation to factor in?" → filer status / CGT awareness (optional).
8. **Constraints** (optional) — sectors to avoid, max crypto exposure, ESG preferences.

**User does:** answers; can go back to edit any step.
**System:** Profiler role evaluates answers → `analyze_profile` writes `risk_profiles` (incl. raw `questionnaire_answers` JSONB); classifies investor mode. Risk = lower of willingness/ability.
**Empty/skip:** tax + constraints optional; the rest required to optimize.
**Next:** Current holdings.

> Design note (DESIGN.md): one question group per view, jade-tinted segmented controls, plain-language descriptions. Calm, not interrogative. The willingness-vs-ability split is the IPS distinction that prevents over-risking a user who *wants* risk but can't afford it.

### Step 2b — Declare current holdings
**Screen:** "Do you already own any investments? Add them so we can factor them in."
- Per holding: asset (search universe — stocks, crypto, gold, T-bills), quantity, **buy price** (PKR per unit → `entry_price`), date bought (optional).
- Add multiple; or "I'm starting fresh" → skip.

**User does:** declares existing positions (what they own + what they paid).
**System:** writes declared `holdings` under the user's portfolio (real positions, not optimizer output). The Optimizer (analyze mode) then evaluates this real portfolio for concentration/risk before proposing a diversified version.
**Next:** Suggested portfolio.

> This is where the "what do you currently hold and at what price" capture happens — feeding analyze-mode diversification. Users starting fresh skip straight to the suggestion.

### Step 3 — Suggested portfolio (Phase 1 output)
**Screen:** the agent's recommendation.
- Allocation **donut** (asset-class colors) with total in the center.
- Expected return, risk, and Sharpe (with SBP risk-free) as mono stat cards.
- **Plain-language rationale** — why this mix, in the agent's voice.
- Holdings list with target weights.
- "Suggested allocation, not financial advice" disclaimer (RULES.md A3.7).

**User does:** reviews; can ask the agent to adjust (opens chat with context), or proceed.
**Actions:** `Confirm holdings` (primary) · `Adjust` (opens chat) · `Start over`.
**Next:** Confirm holdings.

### Step 4 — Confirm holdings (Phase 2 — activation)
**Screen:** "Tell us what you actually invested." Pre-filled with the suggestion, fully editable.
- User can match the suggestion exactly, or change quantities/weights to reflect what they really bought.
- Each line: instrument, quantity, entry price, entry date.

**User does:** confirms their **actual** positions.
**System:** `confirm_holdings` → `portfolios.status = confirmed`, writes `holdings` with actual weights, starts tracking, writes first `portfolio_snapshot`.
**Why it matters (RULES.md A1 / TECH.md):** the agent monitors the *confirmed* portfolio, not the suggestion — users rarely buy exactly what's proposed.
**Next:** Dashboard.

### Step 5 — Dashboard (Phase 3 — monitoring begins)
The user's home from now on. Detailed in §4.

---

## 4. Returning user flow

```
Landing → Log in → Dashboard
```

**Log in:** email + password → JWT → Dashboard. On arrival, the dashboard shows any **pending flags** raised by the background monitor since last visit (badge on the Flags surface). Nothing auto-changed — flags wait for the user.

If a returning user has no confirmed portfolio yet (registered but didn't finish), route them back to the onboarding form at the step they left.

---

## 5. Dashboard (home) flow

The dashboard is the hub. Everything branches from here.

```
┌──────────────────────────────────────────┐
│  Portfolio value (hero)  +  P&L           │
│  Performance line chart                   │
├──────────────────────────────────────────┤
│  Allocation donut   │   Holdings table    │
├──────────────────────────────────────────┤
│  Pending flags (if any)                   │
│  Personalized news (top items)            │
└──────────────────────────────────────────┘
   nav: [ Dashboard ] [ Chat ] [ News ] [ Flags ]
```

**What the user sees:**
- **Hero:** total portfolio value (serif) + P&L (gain/loss color + arrow).
- **Performance** over time (from snapshots).
- **Allocation** donut + **holdings** table with live prices and day change.
- **Flags** preview — any pending material events.
- **News** preview — top items matched to their holdings.

**Where they can go:**
- Tap a holding → holding detail (price history, related news).
- Open **Chat** to ask anything.
- Open **News** for the full personalized feed.
- Open **Flags** to act on alerts.
- Trigger **Re-optimize** (from a flag or manually).

---

## 6. Chat flow

The conversational surface. The agent has the user's full context loaded (profile, holdings, flags).

```
User types ──▶ Agent (streams) ──▶ may render inline cards
                    │
        ┌───────────┼────────────┐
        ▼           ▼            ▼
   text answer  allocation   news/flag
                 mini-card    summary
```

**Typical asks and what happens:**

| User says | Agent does |
|---|---|
| "How is my portfolio doing?" | `track_value` → value, P&L, brief read |
| "Why do I hold so much in banks?" | explains rationale from the optimization |
| "What happened with the rate decision?" | pulls the relevant flag/news → impact on their holdings |
| "Rebalance me" / "adjust this" | runs `reoptimize` → shows a **new suggested** portfolio (does **not** auto-apply) |
| "Should I buy more gold?" | discusses; frames as suggestion, not advice |

**Key rule (RULES.md A1.1):** if the agent proposes a change, it renders a suggestion the user must explicitly confirm. Chat never mutates the portfolio on its own.

**Streaming:** responses stream; tool results (like a suggested allocation) appear as inline mini-cards, not raw text (DESIGN.md).

---

## 7. News flow

```
News feed (filtered to holdings)
   │
   ├─ each item: source · headline · impact chip (↑/↓/→) · level (direct/sector/macro)
   │
   ├─ tap item → detail: full impact, which holdings affected
   │
   └─ a material item may also appear as a Flag (see §7)
```

**What the user sees:** only news relevant to *their* holdings — direct (a ticker they own), sector (their exposure), or macro (portfolio-wide). Each tagged with impact direction and relevance level.

**User does:** browse, tap for detail, or jump to chat to ask "what does this mean for me?"

**Important:** the news feed is informational. It surfaces everything relevant; only the *material* subset becomes a flag that asks for a decision.

---

## 8. Flag → re-optimize flow (the monitoring loop)

This is the product's signature loop — the agent watches, flags, and the user decides.

```
Background monitor (runs on schedule, no user present)
   │
   ▼
Material event matched to holdings ──▶ Flag created
   │
   ▼
User returns / is notified ──▶ sees Flag on Dashboard
   │
   ▼
Opens Flag ──▶ reads what happened + impact rationale
   │
   ├──▶ "Re-optimize"  ──▶ agent suggests adjusted portfolio
   │                          │
   │                          ├──▶ Confirm new holdings ──▶ portfolio updated
   │                          └──▶ Discard ──▶ nothing changes
   │
   └──▶ "Dismiss"      ──▶ flag acknowledged, no change
```

**Step by step:**
1. **Flag appears** (created by `news_monitor` / `rate_impact` / drift). User sees it on the dashboard with a severity color (rust = high, gold = medium).
2. **User opens it:** plain-language explanation — what happened, which holdings, how it affects portfolio risk/return.
3. **User chooses:**
   - **Re-optimize** → agent runs `reoptimize` (factoring in the flag reason) → presents a **new suggested** portfolio.
   - **Dismiss** → flag marked acknowledged; portfolio untouched.
4. **If re-optimizing:** user reviews the new suggestion → **confirms** (portfolio updates, new snapshot) or **discards** (no change).

**Non-negotiable (RULES.md A1.1):** the portfolio never changes without the user's explicit confirm. The agent does every bit of analysis; the decision is always the user's.

---

## 9. Edge & empty states

Treat these as direction, not afterthoughts (DESIGN.md writing rules).

| State | What the user sees |
|---|---|
| No portfolio yet | Dashboard invites: "Build your first portfolio" → onboarding |
| No flags | Calm: "Nothing needs your attention right now." |
| No news matched | "No news affecting your holdings today." |
| Optimization can't run (thin data) | Explain plainly + suggest a broader/liquid universe; never a raw error |
| Data source stale/down | Show last-known value with a quiet "as of [time]" note; don't block the screen |
| Re-optimize discarded | Return to dashboard unchanged; confirm nothing was altered |
| Login while monitor found flags | Dashboard surfaces them immediately, badged |

---

## 10. Notifications (post-MVP note)

For MVP, flags surface **on next visit** (pull model) — no push infrastructure needed. The dashboard badge + flags surface is enough. Push/email notifications for material flags are a post-MVP enhancement; the flag data model already supports it.

---

## 11. Flow ↔ phase ↔ data mapping

| User flow step | Agent phase | Writes to |
|---|---|---|
| Guest "try it" (analyze) | pre-Phase 1 | nothing — session/browser state only |
| Register | — | `users` |
| Onboarding form | Phase 1 | `risk_profiles` |
| Suggested portfolio | Phase 1 | `portfolios` (draft), `holdings` (target) |
| Confirm holdings | Phase 2 | `portfolios` (confirmed), `holdings` (actual), first `portfolio_snapshots` |
| Dashboard / monitoring | Phase 3 | `portfolio_snapshots` (daily), `flags` |
| News feed | Phase 3 | reads `news_items`, `news_holding_link` |
| Flag → re-optimize | Phase 3 | `flags` (resolved), `portfolios` (new draft → confirmed) |

---

*End of FLOW.md. The spine: form → suggestion → confirm → dashboard → (watch → flag → decide) on loop. Every change passes through an explicit user confirm.*
