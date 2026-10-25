# 🏢 NRW Data Center Business Intelligence Platform

### AI-Powered Geospatial Business Intelligence for Data Center Site Selection and Infrastructure Analysis

The NRW Data Center Business Intelligence Platform is an AI-powered decision support system that combines geospatial analysis, infrastructure intelligence, renewable energy data, market intelligence, and conversational AI into a single interactive dashboard.

Built with **Python**, **PostgreSQL/PostGIS**, **GeoPandas**, **PyDeck**, **Streamlit**, and **OpenAI**, the platform enables users to evaluate data center locations through interactive GIS visualization, site scoring, and AI-assisted insights.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Dashboard Modules](#dashboard-modules)
- [AI Advisor](#ai-advisor)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Data Pipeline](#data-pipeline)
- [Project Status](#current-project-status)
- [Roadmap](#roadmap)
- [Vision](#vision)

![Python]
![PostgreSQL]
![PostGIS]
![Streamlit]
![OpenAI]
![Status]

## Overview

Selecting an optimal location for a modern data center requires much more than available land.

Power infrastructure, renewable energy, electrical grid capacity, market activity, and surrounding infrastructure all influence the long-term viability of a site.

The NRW Data Center Business Intelligence Platform integrates multiple public infrastructure datasets into a unified PostgreSQL/PostGIS database and provides an interactive AI-powered dashboard for analyzing, comparing, and evaluating potential data center locations.

The platform combines:

- Geospatial Intelligence
- Infrastructure Analysis
- Site Scoring
- Market Intelligence
- AI-assisted Decision Support

# Key Features

## GIS Intelligence

✔ Interactive GIS Infrastructure Map

✔ Data Center Visualization

✔ High Voltage Substations

✔ Transformers

✔ Transmission Lines

✔ Renewable Energy Assets

---

## Business Intelligence

✔ KPI Dashboard

✔ Site Intelligence

✔ Site Score

✔ Market Intelligence

✔ News Intelligence

✔ Spatial Infrastructure Analysis

---

## Artificial Intelligence

✔ AI Advisor

✔ Natural Language Queries

✔ Executive Infrastructure Summaries

✔ Context-aware Responses

✔ Retrieval-Augmented Generation (RAG)

&nbsp;&nbsp;&nbsp;&nbsp;*Agentic RAG — plan → retrieve → verify → refine → answer over
pgvector-embedded news, with cited, bilingual (German/English) sources. Scope: the
corpus is 40 articles from one German feed (DataCenter-Insider), so it answers
"what regulatory, grid and investment pressures affect data center projects right
now" well, and says so plainly when a question asks about a specific place the
feed never covered, rather than inventing local coverage.*

---

## Spatial Intelligence

✔ Power Readiness Analysis

✔ Renewable Energy Analysis

✔ Infrastructure Distance Calculations

✔ Land Value Integration

✔ Site Ranking

# System Architecture

```mermaid
flowchart TD

A[External Data Sources]

B[ETL Pipelines]

C[PostgreSQL + PostGIS]

D[Repository Layer]

E[Business Services]

F[Interactive Dashboard]

G[Site Intelligence]

H[News Intelligence]

I[AI Advisor]

J[Executive Decision Support]

A --> B
B --> C
C --> D
D --> E

E --> F
E --> G
E --> H

F --> I
G --> I
H --> I

I --> J
```

# Dashboard Modules

## Interactive GIS Map

Visualizes:

- Data Centers
- High Voltage Substations
- Transformers
- Renewable Energy Assets
- High Voltage Transmission Lines

---

## KPI Dashboard

Provides executive metrics for infrastructure assets, facilities, and renewable energy resources.

---

## Site Intelligence

Displays infrastructure proximity, renewable energy availability, land valuation, and technical site characteristics for the selected facility.

---

## Site Score

Calculates a unified infrastructure readiness score using spatial analysis and business intelligence metrics.

---

## News Intelligence

Aggregates recent industry news and links relevant articles to companies and facilities.

---

## AI Advisor

Provides conversational access to infrastructure intelligence using natural language.


# AI Advisor

The AI Advisor enables users to explore infrastructure intelligence using natural language.

Current capabilities

- Site Summaries
- Infrastructure Analysis
- Grid Readiness Evaluation
- Renewable Energy Analysis
- Executive Recommendations
- News Summaries
- Intent Detection
- Tool Routing
- Context Awareness
- Agentic RAG (see [Artificial Intelligence](#artificial-intelligence) for scope)

Upcoming

- LangGraph Agents


# Technology Stack

## Backend

- Python
- SQLAlchemy
- PostgreSQL
- PostGIS

## GIS

- GeoPandas
- Shapely
- PyDeck

## Dashboard

- Streamlit

## AI

- OpenAI
- Retrieval-Augmented Generation (RAG)

## Data Processing

- Pandas
- JSON
- GeoJSON

# Project Structure

```
nrw-dc-bi/
│
├── app/
│   ├── ai/              # OpenAI advisor and prompts
│   ├── commands/        # Thin use-case entry points
│   ├── config/          # DataPaths, external data source definitions
│   ├── database/        # Session, models, repositories
│   ├── enrichers/       # Spatial enrichment (power, land value)
│   ├── exporters/       # Factsheets and map renders
│   ├── extractors/
│   ├── intelligence/    # News and market intelligence
│   ├── loaders/         # Cleaned JSON -> PostgreSQL
│   ├── mergers/
│   ├── news/
│   ├── parsers/         # Raw payloads -> entities
│   ├── runners/         # One runner per pipeline step
│   ├── scorers/         # Site scoring
│   ├── scrapers/        # DataCenterMap, Overpass, MaStR, BORIS
│   ├── services/        # Dashboard-facing services
│   ├── spatial/
│   └── transformers/    # Cleaning and normalisation
│
├── alembic/             # Migration chain
├── data/
│   ├── runs/<run_id>/   # One isolated directory per `main.py all` run
│   └── current/         # Last successfully promoted run
├── scripts/             # Ad-hoc inspection and verification scripts
├── tests/               # pytest suite
├── ui/
│   ├── assets/
│   ├── components/
│   └── app.py           # Streamlit entry point
├── main.py              # Pipeline CLI entry point
└── README.md
```

Repositories live under `app/database/repositories/`, not `app/repositories/`.


# Installation

## Prerequisites

- Python 3.12+
- PostgreSQL 17 + PostGIS
- uv (Python package manager)

Install uv if you don't already have it:

```bash
pip install uv
```

or

```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## Clone the Repository

```bash
git clone <repository-url>

cd nrw-dc-bi
```

---

## Create a Virtual Environment

```bash
uv venv
```

Activate it:

### Windows

```bash
.venv\Scripts\activate
```

### Linux / macOS

```bash
source .venv/bin/activate
```

---

## Install Dependencies

```bash
uv sync
```

If you're not using a `uv.lock` yet, then instead use:

```bash
uv pip install -r requirements.txt
```

---

## Create the Database

PostGIS has to be enabled in the database before migrations run.

```bash
createdb -h localhost -p 5433 -U postgres nrw_dc_bi
psql -h localhost -p 5433 -U postgres -d nrw_dc_bi \
  -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

Adjust the port to match your server — Postgres.app on macOS commonly serves
on 5433, a default Linux install on 5432.

---

## Configure Environment

```bash
cp .env.example .env
```

The application (`app/database/session.py`) and Alembic (`alembic/env.py`)
both read a single `DATABASE_URL`. There are no separate `POSTGRES_*`
variables.

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/nrw_dc_bi
OPENAI_API_KEY=sk-...
```

`OPENAI_API_KEY` is needed by the AI Advisor panel (Agentic RAG news questions
included) and by the two opt-in pipeline steps `news-embed`/`news-signals` — see
[Paid steps](#paid-steps-not-part-of-all). The rest of the dashboard runs without
it; `NewsRetrievalService` degrades to returning no news results rather than
raising if it's unset, so the AI Advisor still answers other questions.
`OPENAI_MODEL` (mini, default `gpt-4.1-mini`), `OPENAI_ANSWER_MODEL` (default
`gpt-4.1`), and `OPENAI_EMBEDDING_MODEL` (default `text-embedding-3-small`,
must stay 1536-dimension) are all optional overrides — see `.env.example`.

---

## Run Database Migrations

```bash
uv run alembic upgrade head
```

This creates the `iris_core` schema and its seven tables, and needs no
manual schema preparation.

---

## Load the Data

**The dashboard reads everything from the database, and the repository ships
with no data.** A fresh install has to run the ETL pipeline before the
dashboard shows anything — see [Data Pipeline](#data-pipeline) for what this
does, how long it takes, and how it can fail.

```bash
uv run python main.py all
```

---

## Start the Dashboard

```bash
uv run streamlit run ui/app.py
```

Available at http://localhost:8501. Against an empty database the panels
render their "no data" states rather than failing.

---

## Run the Tests

```bash
uv run pytest
```

Database tests create and drop their own uniquely-named scratch databases on
the local server and never touch the project database. They skip when no
server is reachable.

---

# Data Pipeline

The dashboard is a read-only view over PostgreSQL. Everything it displays is
produced by the ETL pipeline in `app/runners/`, driven by `main.py`.

## Running the whole pipeline

```bash
uv run python main.py all
```

`all` runs four phases in order, and is the only mode that isolates its
output — see [Staged runs](#staged-runs).

| Phase | Steps | External sources |
|---|---|---|
| 1 — Data Acquisition | `country` → `markets` → `facilities` → `merge` → `transform` → `facility-geo-transform` → `facility-load` | datacentermap.com |
| 2 — Infrastructure | `overpass` → `overpass-parse` → `overpass-transform` → `mastr` → `mastr-parse` → `mastr-transform` → `boris-transform` → `energy-asset-load` | OpenStreetMap Overpass, MaStR registry, BORIS |
| 3 — Spatial Intelligence | `power-enricher` → `boris-enricher` → `site-score` | none — operates on loaded data |
| 4 — Business Intelligence | `news` → `entity-matcher` → `news-load` → `news-intelligence` → `land-values` → `power-infrastructure` → `osm-infrastructure` | RSS feeds |

The country code defaults to `DE` and is overridable with `--country`.

## Paid steps (not part of `all`)

Two steps call OpenAI and are deliberately **not** reachable from any phase, so
`main.py all` stays free and offline-safe. Run them explicitly when you want
Agentic RAG to have something to retrieve:

```bash
uv run python main.py news-embed    # translate + embed every news article (pgvector)
uv run python main.py news-signals  # extract structured signals (expansion/power/
                                     # renewable/retrofit/investment) per article
```

Both are idempotent — re-running either is a no-op for articles whose underlying
text hasn't changed.

## Running a single step

Every step can be run on its own:

```bash
uv run python main.py overpass
uv run python main.py facility-load
uv run python main.py --help      # lists every step
```

A single step runs without a RunContext, so it reads and writes the flat
`data/` workspace rather than a run directory.

## Staged runs

`all` creates `data/runs/<run_id>/` and writes everything beneath it. On
full success the run is promoted to `data/current/`; on any failure nothing
is promoted and `data/runs/<run_id>/run_status.json` records the error. The
existing `data/current/` is never modified until a run succeeds.

Database writes are not part of that staging — they happen inside the
individual load steps (`facility-load`, `energy-asset-load`, `news-load`,
`land-values`, `power-infrastructure`, `osm-infrastructure`).

ETL components resolve paths through `DataPaths` (`app/config/paths.py`)
rather than hardcoding `data/raw` or `data/processed`.

## External sources and rate limits

The acquisition steps make live requests to public sources, so a full run
takes a long time and can fail for reasons that are not bugs:

- **datacentermap.com rate-limits aggressively.** Phase 1's `country` step
  has returned `429 Too Many Requests`; `HttpClient` retries with backoff
  and then aborts the run without promoting it.
- `country` reuses data where it can: the run directory first, then a legacy
  cache at `data/raw/datacentermap/<country>.json`, and only then a fresh
  request. Seeding that file skips the external call entirely.
- `facilities` caches per market and waits 8–15 seconds between fresh
  external requests.
- Phases 2 and 4 use different hosts (Overpass, MaStR, BORIS, RSS) and are
  unaffected by a datacentermap.com rate limit.
# Current Project Status

## Completed

- Data Collection
- ETL Pipelines
- GIS Dashboard
- Interactive Map
- Site Intelligence
- Site Score
- News Intelligence
- AI Advisor
- Infrastructure Layers
- Context-aware AI
- Intent Detection
- Tool Routing
- Agentic RAG (40-article, single-feed scope — see Key Features)

## In Progress

_(nothing currently in progress)_

## Planned

- Multi-Agent AI
- Predictive Site Recommendations
- Investment Forecasting
- Voice Interface
- LangGraph Integration


# Roadmap

## Completed

- ETL Platform
- GIS Visualization
- Business Intelligence Dashboard
- AI Advisor
- News Intelligence
- Intent Detection
- Context-aware Responses
- Agentic RAG

## Next

_(nothing currently in progress)_

## Future

- Predictive Site Ranking
- Multi-Agent Decision Support
- Voice-enabled AI Advisor
- LangGraph Workflows


# Vision

The long-term vision is to build an AI-powered decision support platform for data center planning and infrastructure investment.

By combining geospatial intelligence, power infrastructure, renewable energy, land valuation, market intelligence, and conversational AI, the platform enables users to evaluate and compare potential data center locations through natural language interaction.

The project is designed to evolve into a comprehensive executive decision-support system that assists planners, investors, and infrastructure specialists in identifying optimal data center locations.