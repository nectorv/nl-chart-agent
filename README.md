# NL Chart Agent

Turn natural language questions into interactive data charts.

**Live demo → [frontend-production-50d4.up.railway.app](https://frontend-production-50d4.up.railway.app)**

---

## What it does

Ask a data question in plain English. The agent decides where to fetch the data, retrieves it, picks the right chart type, and renders it — all in one shot.

```
show me S&P 500 vs MSCI World since 2022
evolution of CO₂ emissions per capita in France since 1990
compare Tesla and NVIDIA stock since 2022
show US unemployment rate since 1990
life expectancy in Japan and USA since 1950
```

---

## Architecture

The backend is a **LangGraph pipeline** with 5 stages, each an LLM call or a deterministic transform:

```
Query → Input Guard → Query Planner → Data Fetcher → Schema Reconciler → Chart Planner → Evaluator → Renderer
                                                                                    ↑_______________|
                                                                               (retry loop, max 3x)
```

| Stage | What it does |
|---|---|
| **Input Guard** | Classifies the query: pass / irrelevant / injection / clarification needed |
| **Query Planner** | LLM selects which data source(s) to call and with what arguments |
| **Data Fetcher** | Executes the tool calls (parallel when independent) |
| **Schema Reconciler** | Normalizes types, profiles columns, joins or stacks multi-source datasets |
| **Chart Planner** | LLM maps columns to a Vega-Lite chart spec; falls back to free-form codegen if confidence < 0.6 |
| **Evaluator** | LLM-as-judge scores `data_fit` and `intent_match` (1–5); triggers retry if either < 4 |
| **Renderer** | Assembles the final Vega-Lite spec + provenance metadata |

Progress streams to the UI via **SSE** (Server-Sent Events) so the pipeline trace updates in real time.

---

## Data sources

| Source | What it covers |
|---|---|
| [FRED](https://fred.stlouisfed.org) | US macroeconomic time series — GDP, CPI, unemployment, interest rates, S&P 500, oil, forex… |
| [World Bank](https://data.worldbank.org) | Country-level development indicators — population, GDP, inflation, literacy, CO₂… |
| [Yahoo Finance](https://finance.yahoo.com) | Any stock, ETF, or crypto with full price history (AAPL, BTC-USD, SPY, URTH…) |
| [Our World in Data](https://ourworldindata.org) | Long-run global trends — life expectancy, CO₂ per capita, internet usage, HDI, child mortality… |

Multi-source queries (e.g. "SPY vs URTH") are handled automatically: identical schemas are **stacked** for multi-series charts; mismatched schemas go through LLM-powered column alignment and join.

---

## Tech stack

**Backend**
- Python 3.12, FastAPI, LangGraph
- Anthropic Claude API (query planner, chart planner, evaluator, schema reconciler)
- pandas for data normalization and schema reconciliation
- httpx, yfinance for data fetching

**Frontend**
- React 19, TypeScript, Tailwind CSS
- [Vega-Lite v5](https://vega.github.io/vega-lite/) for chart rendering
- SSE streaming for real-time pipeline trace

**Infrastructure**
- Deployed on [Railway](https://railway.com) (backend + frontend as separate services)
- CI/CD via GitHub Actions on push to `main`

---

## Running locally

### Prerequisites

- Python ≥ 3.12
- Node.js ≥ 20
- API keys: `ANTHROPIC_API_KEY`, `FRED_API_KEY` (free at [fred.stlouisfed.org/docs/api](https://fred.stlouisfed.org/docs/api/api_key.html))

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install .

cp .env.example .env
# Fill in ANTHROPIC_API_KEY and FRED_API_KEY in .env

uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [localhost:5173](http://localhost:5173). The Vite dev server proxies `/api` to the backend on port 8000.

---

## Project structure

```
nl-chart-agent/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routes (SSE streaming, clarification)
│   │   ├── mcp/          # Data source clients (FRED, World Bank, Yahoo, OWID)
│   │   ├── models/       # Pydantic models and Vega-Lite chart specs
│   │   ├── pipeline/     # LangGraph nodes (input_guard, query_planner, …)
│   │   └── utils/        # Logger, data sampling
│   ├── data/             # Static reference datasets
│   └── pyproject.toml
└── frontend/
    └── src/
        ├── components/   # ChartDisplay, PipelineTrace, LoadingChart, …
        ├── hooks/        # useChart — SSE state machine
        └── types/
```

---

## Deployment

Both services are deployed on Railway. On every push to `main`, GitHub Actions redeploys backend then frontend.

To set up CI/CD on a fork:
1. Create a Railway project with two services: `backend` and `frontend`
2. Set environment variables on each service (see `.env.example` for backend; set `VITE_API_URL` to your backend's public URL on frontend)
3. Add `RAILWAY_TOKEN` as a GitHub Actions secret (Railway dashboard → Account → Tokens)
