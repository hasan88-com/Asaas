# Asaas (اثاثہ) — Agentic Wealth Management

**Autonomous analysis, human-approved decisions.**

Asaas is an AI-powered wealth management platform built for the Pakistan market. It analyzes your portfolio using real market data, suggests optimized allocations via Modern Portfolio Theory, monitors news and policy changes, and flags material events — all while keeping every decision in your hands.

## Features

- **Smart Profiling** — risk tolerance, horizon, goals → investor classification
- **Portfolio Optimization** — PyPortfolioOpt with SBP risk-free rate, sector caps, diversification
- **Multi-Asset** — PSX stocks, global equities, crypto, T-bills, commodities
- **Agentic Chat** — conversational interface with tool use and streaming
- **News Monitoring** — automated materiality scoring matched to your holdings
- **Rate Impact** — SBP policy rate changes → T-bill repricing alerts
- **Guest Mode** — try the optimizer without signing up

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.11+), SQLAlchemy, Pydantic |
| Agent | LangGraph, Gemini, Groq, Cerebras, OpenRouter |
| Optimization | PyPortfolioOpt |
| Data | yfinance, CoinGecko, SBP scrape, FRED, Alpha Vantage |
| Database | PostgreSQL 15+, Redis |
| Frontend | React + Vite + TypeScript + Tailwind + shadcn/ui |
| Charts | Chart.js |

## Quick Start

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
cp .env.example .env         # fill in your API keys
alembic upgrade head         # run migrations
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### API Keys Required

| Key | Source | Required |
|---|---|---|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) | ✅ |
| `GROQ_API_KEY` | [Groq Console](https://console.groq.com/) | ✅ |
| `COINGECKO_API_KEY` | [CoinGecko](https://www.coingecko.com/en/api) | ✅ |
| `FRED_API_KEY` | [FRED](https://fred.stlouisfed.org/docs/api/api_key.html) | ✅ |
| `ALPHA_VANTAGE_API_KEY` | [Alpha Vantage](https://www.alphavantage.co/support/#api-key) | ✅ |
| `CEREBRAS_API_KEY` | [Cerebras](https://cloud.cerebras.ai/) | Optional |
| `OPENROUTER_API_KEY` | [OpenRouter](https://openrouter.ai/) | Optional |

## Project Structure

See `BUILD_LOG.md` for the complete file registry and current build state.

## Documentation

- `docs/PRD.md` — Product requirements
- `docs/TECH.md` — Technical spec + DB schema
- `docs/AGENT_RULES.md` — Agent runtime conduct
- `docs/DESIGN.md` — Visual design system
- `docs/FLOW.md` — User flows

---

*Asaas means "asset" or "foundation" in Urdu. Built for Pakistan's retail investors.*
