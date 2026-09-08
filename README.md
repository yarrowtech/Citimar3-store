# CITIMART™ Sales KPI Dashboard

A web-based sales performance dashboard for CITIMART's three stores (New Market,
Hatibagan, Chowringhee), built directly from the `DATASET.xlsx` workbook. It cleans
and standardises the raw POS export, computes a central set of retail KPIs, and
serves an interactive dashboard with filters, charts, tables and a data-quality panel.

This is **Phase A** of a three-phase build:

- **Phase A (this repo today):** data pipeline, KPI engine, and the full interactive
  dashboard website — filters, KPI cards, 18 charts, store scorecards, and the data
  quality panel. CSV download on every table/chart.
- **Phase B (planned):** forecasting module (multiple candidate models, chronological
  validation, forecast charts, model explainability).
- **Phase C:** multi-format report export (PDF/PPTX/DOCX/XLSX/CSV/MD/HTML/XML) with a
  full in-browser editable preview before download — the "Export Report" button on any
  Historical Analytics tab (see `CLAUDE.md`'s "Report export (Phase C)" section for the
  design). Not yet wired up for the Forecast tab. Daily Operations has its own
  standalone per-store export instead (`GET /api/daily/report`, `src/daily_report.py`):
  an Excel workbook of the two data tables, or a PDF adding KPI header, gauges, the
  time-slot chart and same-day context.

## Stack

- **Backend:** FastAPI + pandas/openpyxl/Plotly, serving a pure JSON API under `/api/*`.
  Zero HTML rendering happens server-side.
- **Frontend:** React 18 + TypeScript, built with Vite, styled with Tailwind CSS v4 and
  shadcn/ui (the same Radix + Tailwind foundation 21st.dev components are built on),
  animated with Framer Motion, charts rendered client-side with `react-plotly.js`
  against the exact same Plotly figure JSON the old server-rendered version used, and
  data fetching/caching handled by TanStack React Query (which also solves a real bug
  the previous vanilla-JS frontend had — see "Migration notes" below).
- FastAPI serves the built React app as static files, so a single `uvicorn app:app`
  is still all that's needed to run the whole thing day-to-day; Node is only needed
  when you're actively changing the frontend.

## Features (Phase A)

- Reads `DAY WISE SALE`, `SALES TARGET`, and `TIME WISE FOOTFALL-NOB` from
  `DATASET.xlsx` without ever modifying the source file.
- Alias-based column mapping (`config/column_aliases.py`) so future workbook header
  renames don't require code changes.
- Cleaning pipeline: drops void (`ISVOID = Yes`) rows, drops exact duplicate rows,
  flags (without dropping) same-bill zero-amount duplicate lines, nulls out
  numeric/date contamination in the product hierarchy fields (Product Design No.,
  Product Style, Product Type, Product Size — see "Product hierarchy data quality"
  below), flags non-standard GST rates, derives calendar fields
  (day/week/month/quarter/year/weekend), and standardises store codes.
- Central KPI engine (`src/kpi_engine.py`) — every formula lives in one place and
  returns `None` (rendered as `N/A — required source field not available`) instead of
  a misleading zero when a source field or denominator is missing. Every KPI card
  exposes its formula via an (i) info button so no number is a black box.
- Cascading filters, all server-driven: store → date range → Division → Section →
  Department → Product Design No. → Product Style → Product Type → Product Size →
  Vendors. Every field uses the same searchable-multiselect widget and narrows based
  on everything selected above it in that order.
- 18 Plotly charts (Net vs Gross Sales, Footfall vs NOB, ATV/Conversion/Achievement
  gauges, conversion funnel, monthly sales bridge, daily trend, day-of-week averages,
  target achievement, monthly same-day comparison, yearly same-month comparison,
  category drill-down, top products/brands, gross profit by division, discount impact)
  plus a store scorecard and a Data Quality panel.
- Every table/chart has a matching CSV download that respects the active filters.
- Three UI themes, toggled from the top-bar icon (Light → Dark → **Neon**). "Neon" is a
  dark glassmorphism skin — frosted translucent panels, neon accents, recoloured
  charts/gauges. It is screen-only: exported reports always use the light palette. The
  two Streamlit apps carry the same Default/Neon switch in their sidebar.
- Every rendered chart/table tracks a per-element request token so a slower, now-stale
  response (e.g. from before a filter change) can never overwrite a newer one.

## Project structure

Everything Python lives under `backend/`; the React SPA is its sibling `frontend/`.
`backend/` is self-contained — `config/settings.py`'s `PROJECT_ROOT` resolves to it,
so the workbook, `.cache/`, `img/` and the reports scratch dir all sit inside it. The
one deliberate reach outside is `app.py`'s `FRONTEND_DIST`
(`PROJECT_ROOT.parent / "frontend" / "dist"`), since FastAPI serves the built SPA.

```
├── backend/                     # the entire Python side; run uvicorn/pytest from here
│   ├── app.py                   # FastAPI entrypoint (uvicorn)
│   ├── DATASET.xlsx             # source workbook (never modified)
│   ├── requirements.txt
│   ├── .env                     # local secrets (gitignored); .env.example documents it
│   ├── config/
│   │   ├── settings.py          # paths, store code map, currency, thresholds config
│   │   ├── column_aliases.py    # canonical field -> accepted header spellings
│   │   └── kpi_thresholds.py    # ATV/RTV/Conversion/Achievement/Basket status bands
│   ├── src/
│   │   ├── data_loader.py       # ingestion + mtime-keyed cache under .cache/
│   │   ├── schema_detector.py   # alias resolution (case/whitespace/punctuation tolerant)
│   │   ├── data_cleaner.py      # the full cleaning pipeline
│   │   ├── data_validator.py    # builds the Data Quality panel payload
│   │   ├── filter_engine.py     # cascading store/date + 8-level product hierarchy filters
│   │   ├── kpi_engine.py        # every KPI formula, safe division, N/A handling
│   │   ├── comparison_engine.py # vs-previous-period / vs-month / vs-YoY deltas
│   │   ├── charts.py            # Plotly figure builders
│   │   ├── tables.py            # table builders + CSV export
│   │   ├── formatting.py        # ₹ currency / % / number formatting
│   │   ├── forecasting/         # gated forecast pipeline (see "Forecasting" below)
│   │   └── reports/             # block model + one renderer per export format
│   ├── api/                     # FastAPI routers (filters, kpis, charts, tables, data-quality, meta)
│   ├── db/                      # MongoDB engine/session/models (Daily Operations + auth)
│   ├── scripts/                 # seed_users.py, rotate_passwords.py, ...
│   ├── img/                     # logo assets embedded in PDF/DOCX/HTML/PPTX exports
│   ├── streamlit_app.py         # secondary KPI dashboard UI
│   ├── streamlit_forecast_app.py# secondary forecasting UI
│   └── tests/                   # pytest suite (synthetic DataFrames, not the production workbook)
├── frontend/                    # Vite + React + TypeScript SPA
│   ├── package.json, vite.config.ts, tsconfig*.json, components.json
│   ├── dist/                    # `npm run build` output -- what backend/app.py actually serves
│   └── src/
│       ├── api/client.ts        # typed fetch wrappers for every /api/* route
│       ├── lib/types.ts         # TS mirror of the backend's JSON shapes
│       ├── lib/format.ts        # KPI labels/formulas/formatters (ported 1:1 from the old app.js)
│       ├── components/          # FilterPanel, KpiCard, KpiTable, ChartPanel, DataTable, ui/ (shadcn)
│       └── pages/               # one component per dashboard tab
```

## Prerequisites

- Python 3.11+ (developed against 3.13)
- Node.js 20+ (developed against 24.19.0) / npm — **only needed to build or actively
  develop the frontend**; the built app itself has no Node dependency at runtime
- Windows, macOS, or Linux — no OS-specific code paths

## Environment setup

Python backend:
```
python -m venv .venv
```

Windows:
```
.venv\Scripts\activate
```

macOS/Linux:
```
source .venv/bin/activate
```

Install dependencies:
```
pip install -r backend/requirements.txt
```

Frontend (one-time, or whenever you pull frontend changes):
```
cd frontend
npm install
npm run build
cd ..
```

## Placing DATASET.xlsx

Put `DATASET.xlsx` in `backend/` (next to `app.py`). It must contain the
`DAY WISE SALE`, `SALES TARGET`, and `TIME WISE FOOTFALL-NOB` worksheets — sheets that
are missing or empty are skipped gracefully (reported in the Data Quality panel), not
treated as a crash.

## Running the dashboard

**Day to day (frontend already built):**
```
cd backend
uvicorn app:app --reload
```
Open http://127.0.0.1:8000/ — FastAPI serves the built React app from `frontend/dist/`
plus the `/api/*` routes. No Node process needs to be running. Every backend command
(uvicorn, pytest, `streamlit run`, `python scripts/*.py`) is run from `backend/`.

**Actively developing the frontend** (hot reload): run both, in two terminals —
```
cd backend && uvicorn app:app --reload   # terminal 1, backend on :8000 (or pass --port 8811 etc.)
cd frontend && npm run dev               # terminal 2, Vite dev server on :5173
```
`frontend/vite.config.ts` proxies `/api/*` from :5173 to the FastAPI port, so open the
Vite URL (http://localhost:5173/) while developing. Run `npm run build` again before
shipping/serving through `uvicorn app:app` alone.

The first request after a `DATASET.xlsx` change takes ~90 seconds (parsing ~357K rows
via openpyxl); the cleaned result is cached to `.cache/cleaned_master.pkl`, keyed by
the workbook's modification time, so subsequent restarts are near-instant until the
workbook is next updated.

## Running tests

```
cd backend
pytest
```

The suite uses small synthetic DataFrames and mongomock — it doesn't require
`DATASET.xlsx` or a real database to be present.

## KPI formulas

All formulas live in `src/kpi_engine.py`; thresholds live in `config/kpi_thresholds.py`.
Each formula is also available from its KPI card's (i) info button in the dashboard.
The Daily Operations dashboards have no per-card value override, and the gauges are
read-only. The admin (only) does get the status-band (red/yellow/green) editor on the
five ratio KPI cards — ATV, RPV, Basket Size, Conversion %, Achievement % — editing the
same global overlay as Executive Overview; store managers see those cards read-only. The admin's store selector leads with an **Overall Stores Summary** that
blends all three stores' live daily KPIs (totals summed, ratios recomputed) alongside a
per-store comparison. Store managers get **Manual Data Entry**; the admin does not.

The Achievement % / Remaining KPIs are measured against a per-store, per-date
**Sales Target**. The admin sets these under Daily Operations → *store* → **Sales
Target** (an admin-only view next to Dashboard) — a whole-month grid, one
`Date | Sales Target` row per day, saved in one click, or bulk-loaded from a two-column
(`Date`, `Sales Target`) `.xlsx` via **Upload Excel**. Until an admin sets one, the
midnight job seeds a historical-median estimate so a fresh day still gets a non-N/A
achievement figure.

| KPI | Formula |
|---|---|
| Net Sales (Revenue) | `SUM(net_amount)` |
| Gross Sales | `SUM(gross_amount)`, or `net_amount + discount_amount` when the column is absent (flagged as derived) |
| Gross Profit | `Net Sales − SUM(cogs_with_gst)` |
| Discounts | `SUM(discount_amount)` |
| Bill Quantity | `SUM(bill_quantity)` |
| Footfall | `SUM(footfall)` from `TIME WISE FOOTFALL-NOB` |
| Transactions (NOB) | `SUM(nob)` from `TIME WISE FOOTFALL-NOB` — the source of record for both Footfall and NOB. A distinct-`bill_no`-count from `DAY WISE SALE` is also computed (`nob_transaction_count`) but kept only for cross-checking, not used in any formula. |
| ATV | `Net Sales / NOB` |
| RPV | `Net Sales / Footfall` |
| Basket Size | `Total Quantity Sold / NOB` |
| Conversion % | `NOB / Footfall × 100` |
| Achievement % | `Net Sales / Sales Target × 100` |
| Product Returns (Units) | `SUM(bill_quantity)` where `bill_quantity < 0`, sign-flipped |
| Product Returns (Value) | `SUM(net_amount)` where `net_amount < 0`, sign-flipped |

Any KPI whose required source field can't be resolved renders
`N/A — required source field not available` instead of a fabricated 0.

**Net Profit/Loss is not shown as its own card.** The workbook has no store-expense
data, so it would compute identically to Gross Profit (`Net Sales − COGS with GST`) —
showing both would just duplicate one number under two labels. The field still exists
in `KpiBundle` (`src/kpi_engine.py`) for future use if a distinct expense-based
definition becomes available.

## Product hierarchy data quality

`Product Design No.`, `Product Style`, `Product Type`, and `Product Size` should hold
text codes only, but Excel/openpyxl auto-converted a number of cells in these columns
to actual numbers or dates (e.g. a design code like `1-25` becoming the date Jan-2025,
or a blank "type" cell leaking that row's MRP as a number). `src/data_cleaner.py`'s
`clean_product_hierarchy_fields()` nulls out:

1. any non-string value in these columns (numbers, real `datetime`/`Timestamp`
   objects) — must run before whitespace-stripping stringifies them into
   ordinary-looking text; and
2. any value that was already plain text but still spells out a date (a small number
   of rows hold the literal string `"0168-09-01 00:00:00"` — text, not a real date
   object, but still a "Years" value the field shouldn't hold).

Genuine alphanumeric codes (`FRA-DT-001`, `9-14YRS`, `26/30`) are left untouched. Per-field
counts are reported in the Data Quality tab under "Product hierarchy values nulled".

## Status thresholds

| KPI | Red | Yellow | Green |
|---|---|---|---|
| ATV | < ₹900 | ₹900–1099 | ≥ ₹1100 |
| RPV | < ₹500 | ₹500–699 | ≥ ₹700 |
| Conversion % | < 45% | 45–55% | ≥ 55% |
| Achievement % | < 80% | 80–100% | > 100% |
| Basket Size | < 2 | 2–5 | ≥ 5 |

## Troubleshooting

- **"DATASET.xlsx not found"** — confirm the file sits in `backend/`, next to
  `app.py`, not at the repository root or in a further subfolder.
- **First load is slow** — expected; see "Running the dashboard" above. Delete
  `backend/.cache/cleaned_master.pkl` to force a clean rebuild.
- **`ModuleNotFoundError: No module named 'src'` / `'config'`** — you're running from
  the repository root. `cd backend` first; every Python entrypoint expects that as
  the working directory.
- **A chart/table shows "No data available for the selected filters"** — the active
  store/date/section/department combination has no matching rows; this is the
  intended no-data state, not an error.
- **A KPI shows "N/A"** — the source column it depends on wasn't found in the
  workbook (see the Data Quality tab's "unresolved columns" and `kpi_availability`
  for specifics) or its denominator was zero for the current filter.

## Adding future stores or worksheets

- New stores: add a `CODE: "Full Store Name"` entry to `STORE_CODE_TO_NAME` in
  `config/settings.py`, matching the exact spelling used in the `STORE` column.
- New/renamed workbook columns: add the new header spelling to the relevant list in
  `config/column_aliases.py` — matching is case-insensitive, whitespace-normalised,
  and punctuation/underscore-tolerant, so most header variants resolve automatically.
- New worksheets: extend `REQUIRED_SHEETS` in `config/settings.py` and add a branch in
  `src/data_loader._build_master_dataset` following the existing pattern.

## Migration notes (vanilla JS → React)

The dashboard originally shipped with a Jinja2/vanilla-JS/vendored-Plotly.js frontend
(no Node toolchain at all). It was rebuilt in React/TypeScript/Tailwind/shadcn/Framer
Motion. The backend `/api/*` surface didn't change at all — the React app is a pure
consumer of the same endpoints.

Worth knowing:

- **A real bug got fixed, not just a rewrite.** The old frontend had a request-race
  bug: a slow initial (unfiltered) page-load request could resolve *after* a fast,
  just-clicked filtered request and silently overwrite it with stale data — this is
  what made the Section filter and the Store Scorecard table look like they "weren't
  working." TanStack React Query's query-key-based caching fixes this by construction
  (superseded requests are simply never applied), so there's no hand-rolled
  request-token workaround needed anymore.
- **One additional backend endpoint was added:** `GET /api/meta` (`api/routes_meta.py`)
  — returns the active stores/date-range/last-refresh line the top bar shows. The old
  Jinja2 version computed this server-side at template-render time; since there's no
  server-side rendering anymore, it needed a tiny JSON endpoint instead. No existing
  endpoint or business logic changed.
- **21st.dev** components are normally added by copying an AI-prompt from a specific
  component page into an agent, or via a shadcn-CLI install command each component
  page provides — there was no live browsing session available to pick specific
  component URLs from the site. What's here instead is the exact foundation 21st.dev's
  own install path requires (Tailwind v4 + shadcn/ui + `components.json`), with
  shadcn's core primitives installed. Any genuine 21st.dev component can be dropped in
  later with `npx shadcn@latest add <url>` against this same setup.
- **`Schoepplake/framer-motion-skill`** (a Claude Code skill with Framer Motion
  reference patterns) was added via `claude plugin marketplace add` / `plugin
  install` after confirming the repo is real and contains only a documentation
  `SKILL.md` — no scripts or hooks.
- **`uipro` (`uipro init --ai claude`)** does not exist as an installable package on
  PyPI or the npm registry as far as could be verified. It was not installed.

## Known limitations (Phase A)

- The Phase C block-model report export (editable in-browser preview) covers Historical
  Analytics only — the Forecast tab's 8 sub-tabs each carry their own
  store/horizon/model state beyond the shared filters, so it isn't wired into a static
  per-tab report manifest yet. Daily Operations has a separate standalone per-store
  export (`GET /api/daily/report`) rather than the block-model flow.
- The Store Scorecard table currently exposes some internal field names
  (`gross_sales_is_derived`, `nob_transaction_count`) verbatim; a labelled/curated
  column set is a planned polish item.
- 43,650 rows in `DAY WISE SALE` share a Bill No./Item/Date/Time key with a paired
  ₹0-amount line (flagged as `is_zero_amount_duplicate` in the Data Quality panel, per
  explicit product decision) — these look like a POS export artifact and are worth
  checking against the source POS system, but are kept rather than silently dropped.
- `TERMINAL NO.` / `BILL TIME` are populated on only ~25% of rows across all three
  stores, so bill-time-of-day analysis is only reliable on that subset.
- `Product Design No.`, `Product Style`, and `Vendors` each have thousands of unique
  values; their filter dropdowns render every option client-side (search-filtered, not
  paginated), which is usable but not instant on first render of that panel section.
