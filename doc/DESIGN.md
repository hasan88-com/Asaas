# DESIGN.md — Asaas (اثاثہ)

**Visual system for the frontend**
Pairs with `PRD.md`, `TECH.md`, `RULES.md`. Reference this before building any UI. Stack: React + Vite + Tailwind + shadcn/ui.

---

## 1. Design thesis

Asaas means *asset / foundation*. The interface should feel **grounded, confident, and information-forward** — a serious wealth instrument, not a hype-driven crypto app. It is dense and dashboard-led (everything important visible at a glance), but rendered in a calm, editorial palette so density never tips into noise.

Three principles drive every choice:

1. **Information-forward, not sparse.** A retail investor wants their whole position visible — value, P&L, risk, news, holdings — in one view. Use a dense card grid and a prominent hero value. Density is a feature; calm color and type keep it readable.
2. **Calm palette, confident layout.** The layout can be busy (the paytech-style dense dashboard) *because* the palette is restrained — warm paper, jade, gold, one accent moment per area. We borrow modern dashboard structure but reject the neon-on-black crypto aesthetic.
3. **The dashboard is alive.** Unlike a passive crypto dashboard, Asaas's surfaces are agent-driven: the risk score is computed and explainable, the activity feed is news matched to holdings, flags sit in the grid, and the agent composer is always one tap away.

> Anti-goal: do NOT build the lime-on-black crypto-trader look. Asaas takes the *density and structure* of a modern trading dashboard but renders it warm, paper-toned, and editorial — and weaves the agent through every surface.

---

## 2. Color

A jade-and-gold palette on warm paper. Jade carries growth and stability; gold marks value without being garish; the warm off-white keeps it human rather than clinical. This is the same family as the PRD, so product and documents read as one brand.

### Core palette

| Token | Hex | Use |
|---|---|---|
| `--paper` | `#F6F4ED` | App background (warm off-white) |
| `--card` | `#FFFEFB` | Card / surface background |
| `--ink` | `#16201C` | Primary text (near-black, slight green) |
| `--ink-soft` | `#4A564F` | Secondary text |
| `--ink-faint` | `#7C867F` | Captions, metadata, placeholders |
| `--line` | `#DCD8CC` | Borders, dividers |
| `--line-soft` | `#E8E4D9` | Subtle inner borders |

### Brand & accent

| Token | Hex | Use |
|---|---|---|
| `--jade` | `#0F6E56` | Primary brand, primary buttons, links, positive emphasis |
| `--jade-soft` | `#E1F1EA` | Jade tint backgrounds, selected states |
| `--gold` | `#B8801A` | Accent — value highlights, secondary emphasis |
| `--gold-soft` | `#F6ECD6` | Gold tint backgrounds |

### Semantic (data & status)

| Token | Hex | Use |
|---|---|---|
| `--gain` | `#0F6E56` | Positive P&L, gains (uses jade — green = up) |
| `--loss` | `#A8401F` | Negative P&L, losses (rust, not pure red — calmer) |
| `--loss-soft` | `#F6E3DA` | Loss tint background |
| `--flag-high` | `#A8401F` | High-severity material flag |
| `--flag-med` | `#B8801A` | Medium-severity flag |
| `--neutral` | `#4A564F` | Neutral / no-change |
| `--info` | `#2F4858` | Informational, macro context (slate) |
| `--info-soft` | `#E2E9EE` | Slate tint background |

### Asset-class accents (for charts & tags)

Each asset class gets a consistent hue across the allocation chart, holdings list, and news tags.

| Class | Token | Hex |
|---|---|---|
| PSX / global stocks | `--ac-stock` | `#0F6E56` (jade) |
| Crypto | `--ac-crypto` | `#5A3D6B` (plum) |
| T-bills / fixed income | `--ac-tbill` | `#2F4858` (slate) |
| Commodities | `--ac-commodity` | `#B8801A` (gold) |
| Mutual funds | `--ac-fund` | `#3E7C8C` (teal) |

### Color rules

- **Green is up, rust is down.** Never invert. Gains use `--gain` (jade), losses use `--loss` (rust — deliberately calmer than alarm-red so the dashboard doesn't feel panicky on a normal down day).
- **Gold is for value, not warning.** Use gold for highlighting amounts and accents; medium-severity flags reuse it sparingly.
- **No pure black, no pure white.** Use `--ink` and `--card`. Keeps the interface warm.
- **Dark mode (optional, post-MVP):** invert to a deep forest-ink ground `#101814` with `--paper` text; keep jade/gold accents. Do not build until core is done.

---

## 3. Typography

Three roles, chosen to feel editorial and considered rather than default-SaaS. The pairing signals a publication you trust, not an app shouting at you.

| Role | Typeface | Fallback stack | Use |
|---|---|---|---|
| **Display** | **Fraunces** | `"Fraunces", Georgia, serif` | Headlines, hero numbers, section titles |
| **Body** | **Inter** | `"Inter", system-ui, sans-serif` | All UI text, labels, paragraphs |
| **Data / mono** | **IBM Plex Mono** | `"IBM Plex Mono", ui-monospace, monospace` | Prices, tickers, percentages, metadata, eyebrows |

**Why this pairing:** Fraunces is a soft, high-contrast serif with warmth and authority — it makes a portfolio value feel substantial and considered. Inter keeps the dense UI legible and neutral. IBM Plex Mono gives numbers and tickers a precise, tabular character (and aligns columns of figures cleanly). This is deliberately *not* the all-Inter or all-system look most fintech apps default to.

### Type scale

| Token | Size / line-height | Weight | Typeface |
|---|---|---|---|
| `display-xl` | 48 / 1.05 | 600 | Fraunces |
| `display-l` | 34 / 1.1 | 600 | Fraunces |
| `heading` | 24 / 1.2 | 600 | Fraunces |
| `subheading` | 19 / 1.3 | 500 | Inter |
| `body` | 16 / 1.6 | 400 | Inter |
| `body-sm` | 14 / 1.5 | 400 | Inter |
| `caption` | 12 / 1.4 | 500 | IBM Plex Mono |
| `eyebrow` | 11 / 1.4, +0.18em tracking, uppercase | 600 | IBM Plex Mono |
| `data-l` | 32 / 1.1, tabular-nums | 500 | IBM Plex Mono |
| `data` | 16 / 1.3, tabular-nums | 500 | IBM Plex Mono |

### Type rules

- **All numbers use `font-variant-numeric: tabular-nums`** so columns of prices and percentages align. Non-negotiable for any financial table.
- **Hero portfolio value uses `display-xl` in Fraunces**, with the currency label in small mono beside it.
- **Tickers and prices are always mono** (`HBL.KA`, `₨ 142.50`, `+2.4%`).
- **Sentence case everywhere** except `eyebrow` (uppercase) — no Title Case Buttons.
- Load only the weights used (Fraunces 600, Inter 400/500/600, Plex Mono 500/600) to keep the bundle light.

---

## 4. Spacing, radius, elevation

| Token | Value | Use |
|---|---|---|
| Spacing base | 4px grid | All margins/padding are multiples of 4 |
| `radius-sm` | 6px | Inputs, tags, small controls |
| `radius` | 10px | Cards, buttons |
| `radius-lg` | 14px | Modals, large panels |
| `shadow-sm` | `0 1px 2px rgba(22,32,28,.05)` | Resting cards |
| `shadow` | `0 4px 16px rgba(22,32,28,.08)` | Raised cards, dropdowns |
| `shadow-lg` | `0 12px 32px rgba(22,32,28,.12)` | Modals |

- **Generous whitespace.** Cards breathe (20–24px internal padding). Density is the enemy of trust here.
- **Low, soft shadows** tinted with the ink color (not gray) — keeps elevation warm and subtle.
- **Borders before shadows** for most surfaces — a 1px `--line` border reads cleaner than a heavy shadow on the paper ground.

---

## 5. Component style

Built on shadcn/ui, restyled to the tokens above. Keep shadcn's accessibility and structure; replace its default neutral palette with the Asaas tokens.

### Buttons
- **Primary:** `--jade` background, `--card` text, `radius`, medium weight. Hover: darken ~8%. The main action on any screen.
- **Secondary:** `--card` background, `--ink` text, 1px `--line` border. For secondary actions.
- **Ghost:** transparent, `--ink-soft` text, no border. For tertiary/inline actions.
- **Destructive / caution:** `--loss` background — used only for genuinely destructive actions, never for routine flows.
- Labels say what happens: "Confirm holdings", "Re-optimize", "Dismiss flag" — active voice (per RULES.md writing standards).

### Cards
- `--card` background, 1px `--line` border, `radius`, `shadow-sm`.
- Section eyebrow in mono uppercase at top; content below. Optional 3px top accent bar in the relevant asset-class or status color.

### Data display
- **Portfolio value card:** the hero. `display-xl` Fraunces value, mono currency label, P&L below in `--gain`/`--loss` with a small directional arrow.
- **Holdings table:** mono tabular numbers, asset-class color dot per row, sticky header in `eyebrow` style. Right-align all numeric columns.
- **Allocation chart:** donut using asset-class accent colors; center shows total value; legend in mono.
- **Performance chart:** line/area in `--jade`, soft `--jade-soft` fill, mono axis labels, subtle `--line` gridlines.

### Flags & alerts (the monitoring surface)
- **Material flag card:** left border 3px in `--flag-high` or `--flag-med`, tinted background (`--loss-soft` / `--gold-soft`), headline in `subheading`, impact rationale in `body-sm`, and a clear "Review" / "Re-optimize" action. The flag must feel important but not alarming — it informs, it doesn't panic.
- **News feed item:** compact row, source tag (mono), impact direction chip (↑ `--gain` / ↓ `--loss` / → `--neutral`), headline, relevance level badge (`direct` / `sector` / `macro`).

### Tags & chips
- `radius-sm`, mono `caption`, tinted background of the relevant token. Asset-class tags use the class accent; status chips use semantic colors.

### Forms (onboarding)
- Inputs: `--card` background, 1px `--line`, `radius-sm`, focus ring in `--jade`.
- Clean labels above fields in `body-sm`; help text in `caption`/`--ink-faint`.
- The risk/horizon selectors can use segmented controls (shadcn toggle group) tinted jade when active.

### Chat interface
- User messages: `--jade-soft` bubble, right-aligned.
- Agent messages: `--card` bubble with `--line` border, left-aligned; tool-result cards (e.g. a suggested allocation) render inline as mini cards, not raw text.
- Streaming: show a calm typing indicator, not a spinner.

---

## 5b. Charts

Library: **Chart.js** (in the stack). Charts must read as part of the editorial system — no default Chart.js look. Every chart uses the tokens below.

### Shared chart rules
- **Asset-class colors are fixed** — the donut, legends, and any per-class series always use the §2 asset-class accents (stocks jade, crypto plum, T-bills slate, commodities gold, funds teal). A class is the same color everywhere in the app.
- **Axis labels and legends in IBM Plex Mono**, `--ink-faint`, 11px. Currency formatted (`₨1250K`, `₨ 1,284,500`).
- **Gridlines are hairline `--line`**, horizontal only; never draw vertical gridlines or chart borders.
- **No point markers at rest** on line charts — show a single `--jade` point only on hover, with an ink tooltip.
- **Tooltips:** `--ink` background, mono text, no color swatch box, 10px padding.
- **Round every displayed number** — no floating-point artifacts in labels or tooltips.
- **Respect reduced motion** — disable the entry animation when set.

### Allocation donut
- `type: doughnut`, `cutout: 68%`.
- Segment colors = asset-class accents; 3px `--card` border between segments for separation.
- **Center label:** total value in Fraunces (serif), with a mono "Total" eyebrow above. Rendered as an HTML overlay, not on the canvas.
- Legend rendered as HTML rows below (not Chart.js's built-in legend): color dot + class name (`--ink-soft`) + weight % (mono, bold, right-aligned).

### Performance line
- `type: line`, `tension: 0.35` (gentle curve), `borderWidth: 2.5`, `borderColor: --jade`.
- `fill: true` with `--jade` at ~10% opacity (`rgba(15,110,86,0.10)`) for the soft area.
- Y-axis: PKR values in mono; X-axis: time labels in mono; no vertical grid.
- Sourced from `portfolio_snapshots` (TECH.md §7) — one point per daily snapshot.

### Other chart types
- **Sparklines** (per-holding mini-trends): jade stroke, no axes, no fill, 1.5px — inline in the holdings table.
- **Bar** (e.g. sector exposure): single jade fill, mono axis, hairline baseline only. Use sparingly; the donut covers most allocation needs.
- Avoid pie (use donut), avoid 3D anything, avoid dual-axis charts.

---

## 5c. Agent conversation components

Asaas is a conversation with seven agent roles (profiler, optimizer, news, rate-impact, valuation, technical, chat). The chat surface is the product's spine, so its components carry the most craft. This section specs the shared chat shell, the per-agent result cards, and the surfaces they live in.

> Animation philosophy (applied throughout): motion has a *purpose* or it doesn't exist. The chat is used many times per session, so message appearance is restrained — no bouncy entrances, no decorative flourishes. Custom easing curves, exit faster than enter, and `prefers-reduced-motion` respected everywhere. Easing tokens used below:
> ```css
> --ease-out: cubic-bezier(0.23, 1, 0.32, 1);   /* entrances, feedback */
> --ease-in-out: cubic-bezier(0.77, 0, 0.175, 1); /* on-screen movement */
> ```

### 5c.1 The chat shell (shared by all agents)

The container every agent conversation lives in.

- **Message list** — vertical, generous line spacing, scroll-anchored to bottom. New messages enter with `opacity 0→1` + `translateY(6px→0)` over **200ms `--ease-out`**. No scale, no bounce — messages slide up gently into place (nothing appears from nothing).
- **User message** — `--jade-soft` bubble, right-aligned, `radius` with the bottom-right corner tightened (`radius-sm`) to anchor it to the sender. Ink text.
- **Agent message** — `--card` bubble, `--line` border, left-aligned, bottom-left corner tightened. A small mono agent label above the first bubble in a turn (e.g. `VALUATION` in the asset-class/role accent) so the user knows which role is speaking.
- **Streaming indicator** — three dots with a calm staggered opacity pulse (`ease`, ~1s loop), NOT a spinner. Replaced token-by-token as text streams in; the bubble grows by transition (height/opacity), never a keyframe restart (so rapid streaming retargets smoothly — the Sonner principle).
- **Tool-running state** — when an agent calls a tool, show an inline pill inside the bubble: a slowly rotating 1.5px ring + mono label ("Running optimization…", "Fetching prices…"). The ring is the *only* continuous motion permitted in chat, and it's brisk (fast spin reads as faster work).
- **Send** — Enter sends; button `:active` scales to `0.97` over **120ms** for press feedback. No animation on the send itself (keyboard-initiated, happens constantly).
- **Disclaimer footer** — every agent turn that contains a suggestion ends with the quiet "suggested allocation, not financial advice" line in `caption`/`--ink-faint`.

### 5c.2 Inline result cards (per agent)

When an agent returns structured output, it renders as an inline mini-card *inside* the conversation — not raw text, not a full page. Each card: `--card`, `--line` border, `radius`, a 3px top accent in the agent's color, a mono eyebrow naming the agent, and content. Cards enter with the same 200ms slide-up; if a card contains a chart, the chart's own entry (§5b) plays *after* the card settles (staggered ~80ms), so the container arrives first, then the data draws in.

**Profiler card** — accent `--info` (slate)
- Shows the evaluated profile as a compact summary: risk (with the willingness/ability split noted), horizon, goal, capital band.
- A one-line plain-language read ("You're a moderate investor with a medium horizon, focused on growth").
- Primary action: `Confirm profile`. The profile chips fill with `--jade-soft` as confirmed.

**Optimizer card** — accent `--jade`
- Allocation **donut** (§5b) + expected return / risk / Sharpe as mono stat cells.
- Rationale in `body-sm`.
- Actions: `Confirm holdings` (primary) · `Adjust` (opens a follow-up turn).
- In analyze mode (existing holdings): shows **current vs. suggested** side by side — two small donuts, with the concentration callout ("70% banking") in `--loss` text to flag the risk without alarm.

**News card** — accent `--pink`/rose
- A short list of matched items, each a compact row: source tag (mono), headline, impact chip (↑ `--gain` / ↓ `--loss` / → `--neutral`), level badge (`direct`/`sector`/`macro`).
- Rows stagger in at 40ms intervals (decorative, never blocks).
- No action — informational; material items surface separately as flags.

**Rate-impact card** — accent `--amber`/gold
- States the SBP move, then the dual effect on the user's T-bills in plain language ("market value dips ~X%, reinvestment yield improves").
- A tiny before/after on the fixed-income value.
- Action (if material): `Review & re-optimize`.

**Valuation card** — accent `--info` (slate)
- The headline: intrinsic value estimate (DCF) in serif, beside current price.
- The Monte Carlo **range** as a horizontal band (p10–p90) with the current price marked on it — instantly shows whether the market price sits inside, below, or above the fair-value range. This is the card's hero; it draws the band, then animates the price marker into position (200ms `--ease-out`).
- Multiples row: P/E, EV/EBITDA, P/B vs. peer median (mono).
- **Data-gap notice** when PSX fundamentals are thin: a quiet `--ink-faint` line ("Limited fundamentals for this stock — showing multiples only"), never an error state.
- Framed as estimate; disclaimer footer.

**Technical card** — accent `--plum`
- A compact indicator panel: RSI (with a 0–100 gauge, the needle easing to position), MACD state, MFI, key MAs, and any cross (golden/death) called out as a labeled chip.
- A price line with the relevant MAs overlaid (§5b styling); support/resistance as faint dashed `--line` horizontals.
- Conflicting signals shown side by side, not resolved ("RSI overbought, but MACD still bullish").
- Signals as context; no buy/sell language.

**Chat (general) replies** — accent `--jade`
- Plain prose in the agent bubble; no card unless a tool returned structured data.

### 5c.3 The surfaces (where conversations live)

**Full chat page** — the dedicated conversation surface.
- Message list (§5c.1) fills the column; composer pinned to the bottom with a hairline `--line` top border and a subtle `--card` elevation so it reads as a fixed input layer.
- Empty state: a calm prompt ("Ask about your portfolio, a stock's value, or the technicals for any holding") with 3–4 tappable example chips that seed a first message. Chips have `:active` scale-down feedback only.
- Role transitions are invisible — the user never picks an agent; the orchestrator routes and the speaking role is shown by the mono label. No tabs, no agent-switcher UI.

**Dashboard-embedded chat** — a docked composer at the dashboard edge.
- Tapping it expands the conversation as a drawer (`--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1)`, ~300ms) from the bottom on mobile / side on desktop. Drawer, not modal — it's a frequent companion, so it slides from its edge (spatial consistency) rather than fading centered.
- Exit is faster than enter (~200ms) — snappy dismiss.

**Inline analysis surfaces** (valuation / technical) — these can be reached two ways: asked in chat (→ inline card) or opened from a holding's detail view (→ the same card, full-width). The card component is identical; only its container width differs. Build the card once, place it in both.

**Flag → conversation bridge** — opening a flag can start a conversation pre-seeded with that flag's context ("This rate change affects your T-bills — want me to re-optimize?"). The flag card morphs into the first agent message rather than navigating away abruptly (shared-element feel: the flag's text becomes the bubble's text).

### 5c.4 Cross-agent consistency rules

- **One voice, seven roles.** Every card uses the same shell, the same disclaimer, the same suggestion-not-advice posture. The accent color is the *only* per-agent difference in chrome — so the product feels like one assistant, not seven bots.
- **Cards never auto-act.** Any card proposing a change (optimizer, rate-impact) surfaces an explicit confirm action; the card itself changes nothing.
- **Result before reasoning.** When a card has both a number and an explanation, the number/visual lands first, the prose follows — users scan the result, then read why.
- **Motion budget.** In a single agent turn, at most one "hero" animation (the donut draw, the Monte Carlo band, the RSI gauge). Everything else is the standard 200ms slide-up. Never stack competing animations in one turn.

---

## 5d. Dashboard layout (information-forward)

The dashboard is the product's home — a dense, single-view command center inspired by modern trading dashboards, rendered in the Asaas palette and woven with the agent. Structure:

```
┌────────────────────────────────────────────────────────────┐
│ NAV: Asaas اثاثہ · Dashboard Portfolio Chat News Analysis   │
│      profile pill · search · alerts                          │
├──────────────────────────────────────┬─────────────────────┤
│ Portfolio value (hero, serif)         │ Risk Score          │
│ +delta · time ranges                  │ (agent-computed,    │
│ ┌──────────────────────────────────┐ │  explainable bar)   │
│ │ Performance chart (jade line)    │ │ "Why? Ask agent →"  │
│ └──────────────────────────────────┘ ├─────────────────────┤
│ ┌────┬────┬────┬────┐ metric strip   │ News matched to     │
│ │P&L │P&L │ret │Shrp│ (mono numbers) │ holdings (card grid,│
│ └────┴────┴────┴────┘                 │ impact + materiality│
│                                       │ tags; flags here)   │
├──────────────────────────────────────┴─────────────────────┤
│ AGENT COMPOSER (docked, dark bar) · example chips · send    │
└────────────────────────────────────────────────────────────┘
```

**Layout rules:**
- **Two columns:** wide left (value + chart + metrics), narrower right (risk score + activity feed). Collapses to single column on mobile.
- **Hero value** in Fraunces, big; delta in mono with gain/loss color + arrow.
- **Time-range pills** (1d/1w/1m/6m/1y) — mono, selected fills jade.
- **Metric strip** — 4 compact cards (realized/unrealized P&L, expected return, Sharpe), mono numbers, tied to the optimizer's output (SBP risk-free noted).
- **Risk Score** — a horizontal bar, but *agent-computed* and explainable: a "Why this score? Ask the agent →" link opens chat seeded with that question. This is the key difference from a passive dashboard.
- **Activity feed = news matched to holdings**, not raw transactions. Each card: type, source + relevance level (direct/sector/macro), symbol, impact, and a materiality tag (`material` / `review & re-optimize` / `informational`). Agent flags (rate-impact, drift) live in this grid, the material one highlighted in `--jade-soft`.
- **Docked agent composer** — a dark (`--ink`) bar pinned at the bottom with a mono "Asaas agent" label, placeholder, example chips, and send. Always one tap from a conversation. The single dark element on the paper ground — it anchors the agent as the product's spine.

**Why the composer is dark on paper:** it's the one deliberate contrast — the agent is the differentiator, so its entry point gets visual weight without recoloring the whole UI. Everything else stays warm/calm.

---

## 6. Motion

Restrained. Motion confirms actions and guides attention; it never decorates.

- **Transitions:** 150–200ms ease-out for hovers, state changes, and disclosure.
- **Page/section reveal:** subtle fade-up (8px, 250ms) on first load only — not on every re-render.
- **Numbers:** portfolio value and P&L may count-up on first load (400ms) — a single considered moment, used once per view.
- **Flags:** a new material flag slides in gently and may pulse its border once — then rests.
- **Respect `prefers-reduced-motion`:** disable all non-essential animation when set. Mandatory.

---

## 7. Iconography & imagery

- **Icons:** `lucide-react` (ships with the stack), 1.5px stroke, sized to the text beside them. Use `--ink-soft` resting, `--jade` active.
- **No stock photography.** This is a data product; imagery is charts and the data itself.
- **Empty states** get a simple line illustration or icon + a directive line ("No holdings yet. Build your first portfolio.") — an invitation to act, per the writing rules.
- **Logo / wordmark:** "Asaas" set in Fraunces 600; the Urdu اثاثہ may appear as a secondary lockup. Jade on paper, or paper on jade.

---

## 8. Accessibility (quality floor — non-negotiable)

- **Contrast:** all text meets WCAG AA (4.5:1 body, 3:1 large). Verify `--ink-faint` on `--paper` and gold-on-paper combinations specifically.
- **Never color alone:** gains/losses and flag severity always pair color with a symbol or label (arrow, +/−, severity word) — critical for color-blind users reading financial data.
- **Focus visible:** every interactive element shows a clear `--jade` focus ring.
- **Keyboard:** full keyboard navigation; chat sendable via Enter.
- **Reduced motion:** respected throughout (§6).
- **Touch targets:** minimum 44×44px on mobile.

---

## 9. Tailwind token mapping

Define these in `tailwind.config.js` so components reference semantic names, not raw hex:

```js
theme: {
  extend: {
    colors: {
      paper: '#F6F4ED', card: '#FFFEFB',
      ink: { DEFAULT: '#16201C', soft: '#4A564F', faint: '#7C867F' },
      line: { DEFAULT: '#DCD8CC', soft: '#E8E4D9' },
      jade: { DEFAULT: '#0F6E56', soft: '#E1F1EA' },
      gold: { DEFAULT: '#B8801A', soft: '#F6ECD6' },
      gain: '#0F6E56', loss: { DEFAULT: '#A8401F', soft: '#F6E3DA' },
      info: { DEFAULT: '#2F4858', soft: '#E2E9EE' },
      ac: { stock:'#0F6E56', crypto:'#5A3D6B', tbill:'#2F4858',
            commodity:'#B8801A', fund:'#3E7C8C' },
    },
    fontFamily: {
      display: ['Fraunces','Georgia','serif'],
      sans: ['Inter','system-ui','sans-serif'],
      mono: ['"IBM Plex Mono"','ui-monospace','monospace'],
    },
    borderRadius: { sm:'6px', DEFAULT:'10px', lg:'14px' },
  }
}
```

---

## 10. Do / Don't

| Do | Don't |
|---|---|
| Make the portfolio value the visual hero | Bury it in a grid of equal-weight numbers |
| Use rust (not alarm-red) for losses | Make a normal down-day feel like an emergency |
| Pair color with symbol/label for all status | Rely on red/green alone |
| Use a dense, information-forward grid kept readable by calm color | Add visual noise — clashing accents, heavy borders, decoration |
| Use tabular mono for all figures | Let numbers jitter in a proportional font |
| Let the flag card be calm but clear | Use flashing, pulsing, or pressuring alerts |
| Keep one accent moment per view | Decorate every element with gold |

---

*End of DESIGN.md. The signature of Asaas: a warm, paper-toned, editorial wealth interface where the portfolio value is set in a confident serif and every number is precise mono — calm, grounded, trustworthy.*
