---
title: MuleGraph API
emoji: 🔎
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
---

# MuleGraph · Editorial Intelligence

A complete local research workflow for financial transaction-network investigations: data import → configurable graph rules → ML training and temporal evaluation → interactive evidence exploration → human review and exports.

**Research software, not a certified AML platform.** Source labels are synthetic ground truth, not proof of wrongdoing. Nothing freezes accounts, files regulatory reports, or connects to live banks. The reference artwork is visual inspiration only; fictional identities, legal claims, and confidence figures are not copied into the product.

## Run locally (Windows / PowerShell)

### One-time dependency setup

From this repository (skip this if dependencies are already installed):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
Push-Location frontend
npm.cmd ci
Pop-Location
```

### Start and stop manually

Servers do **not** start when you open the project or activate `.venv`. Use two separate PowerShell terminals. Each command below stays attached to its terminal and shows logs there; nothing launches hidden or detached.

Terminal 1 — backend:

```powershell
cd "D:\hackaton,projects\Mule Graph"
.\start-local.ps1 backend
```

Terminal 2 — frontend:

```powershell
cd "D:\hackaton,projects\Mule Graph"
.\start-local.ps1 frontend
```

Open **http://127.0.0.1:5173** in Chrome. API docs: **http://127.0.0.1:8000/docs**. **Press Ctrl+C in the corresponding terminal to stop that server.** Wait for its shutdown output and the PowerShell prompt. If a long-running import or training job is active, stop submitting work and allow it to finish before shutting down.

Running `./start-local.ps1` without a server only prints help; it starts nothing. Optional backend code watching is explicit: `./start-local.ps1 backend -Reload`. The helper uses the project's virtual environment directly; activation is not required. It refuses occupied ports without killing another process or silently moving to another port.

Alternatively, start the backend directly in the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app `
  --host 127.0.0.1 `
  --port 8000
```

Or start the frontend directly:

```powershell
cd "D:\hackaton,projects\Mule Graph\frontend"
npm.cmd run dev
```

**Do not run both the helper and the direct command for the same server.** Ctrl+C only controls the process attached to the terminal where you press it; it cannot stop a server started elsewhere. A previously opened browser tab is not evidence that a stopped server is still running—it can keep already-loaded content visible.

The optional `.\.venv\Scripts\python.exe -m backend.cli demo` command imports deterministic, explicitly illustrative scenarios and runs the rules; it does not start a server or fabricate performance on IBM/SAML/AMLSim. Skip it to start empty and import actual source files from **Datasets & analysis**.

Use `.env` for real configuration and start Uvicorn with `--env-file .env`; do not put production secrets in `.env.example`. With no `DATABASE_URL`, local development uses SQLite in `MULEGRAPH_DATA_DIR`. Deployment uses Supabase PostgreSQL for transactions, investigations, audit history, and serialized model artifacts; the Render filesystem is used only for disposable upload staging. The UI access key is stored only in sessionStorage, never compiled into the frontend.

## Included

- FastAPI + indexed PostgreSQL in deployment and SQLite/WAL locally, one bounded background worker, persistent job/run history.
- Streaming adapters for prepared CSV/CSV.GZ, IBM raw (including duplicate Account column names), SAML raw, and AMLSim raw.
- Source-row provenance, preserved exact monetary strings, currencies, timestamps/steps, validation summaries, rejected-row examples, and separate label storage.
- Fan-in/out, rapid pass-through, bursts, bounded temporal cycles, observed dormancy, optional shared-device clusters.
- Isolation Forest and optional class-balanced Random Forest with chronological train/validation/test splits, past-only features, threshold selection on validation, PR-AUC/precision/recall/F1 and confusion matrix.
- React + TypeScript + Cytoscape: overview, filtered alerts, directed graph, playback, account dossiers, transaction paging, data setup, model cards, notes, review status, CSV/JSON evidence, audit history.
- Free-tier Render stateless Docker API, Supabase PostgreSQL persistence, and Vercel frontend configuration.

## Source datasets

Existing source folders are never overwritten. Local import detects:

| Source | Prepared file | Semantics |
| --- | --- | --- |
| IBM | `mule-graph-SHIBANKAR-data/MuleGraph/transactions_prepared.csv.gz` | Minute timestamps; paid and received amounts/currencies; transaction labels |
| SAML | `rindaw_data/MuleGraph_Output/transactions_prepared.csv` | Second timestamps; received amount absent; transaction/typology labels |
| AMLSim | `AMLSim/AMLSim/transactions_prepared.csv` | Simulation steps, unknown currency; account labels, not transaction labels |

Local imports automatically read a matching `source_labels.csv[.gz]` sidecar. Prepared CSV uploads do not invent labels; train unsupervised or use the local CLI with `--labels` when preparing a labeled server collection.

```powershell
.\.venv\Scripts\python.exe -m backend.cli import --source ibm --limit 25000
.\.venv\Scripts\python.exe -m backend.cli import --csv prepared.csv --labels source_labels.csv --name "My research" --limit 100000
```

Import limits apply to **first source rows**, not balanced, random, or chronological sampling. All analysis queries then sort by time. The original IBM file is not sorted; an imported prefix is not a full chronological population. Use a deliberately prepared temporal subset with surrounding network context for a fair benchmark. Never cherry-pick known positive cases and report their results as general performance.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
cd frontend
npm run build
npm run test:e2e
```

Browser tests expect the API on port 8000 and Vite on port 5173. Install the Playwright Chromium browser if not already present: `npx playwright install chromium`. Tests use an illustrative dataset and do not alter original source data.

See [architecture](docs/ARCHITECTURE.md), [deployment](docs/DEPLOYMENT.md), [Agile delivery board](docs/DELIVERY.md), and [limitations](docs/LIMITATIONS.md).
