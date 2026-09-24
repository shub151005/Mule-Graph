# Architecture and contracts

```text
React / TypeScript / Cytoscape (Vercel)
             | HTTPS / JSON / API key / configured CORS
FastAPI API (single Uvicorn worker)
   |         |                 |
Import job   Analysis job      Training job
   |         |                 |
CSV adapters temporal rules    past-only features → ML → model card
   |         |                 |
SQLite / WAL: transactions, isolated labels, runs, alerts, notes, audit
Persistent local volume: SQLite and server-generated model artifacts
```

## Boundaries

- `ingest.py`: raw/prepared adapters and deterministic sandbox generator. Decimal validates amounts; original decimal strings are persisted. No currencies or clock times are inferred from missing fields.
- `analysis.py`: bounded chronological rule engine and causal feature extraction. Equal-time rows do not see each other in their input features. Window units are seconds or simulation steps depending on source.
- `ml.py`: deterministic training, temporal split, validation-only threshold selection, model persistence, post-training anomaly inference.
- `db.py`: SQLite schema, transactions, helpers and audit events.
- `jobs.py`: serialized background jobs, progress, queue cap of three, crash recovery marking interrupted jobs. One Uvicorn worker is required.
- `main.py`: constrained HTTP contracts, uploads, query endpoints, key authentication, CORS, evidence export with spreadsheet-formula protection.
- `frontend/src`: live API client, page components, graph lifecycle, and responsive editorial design system.

## Money, time, and labels

Identifiers remain strings and retain leading zeros. The database isolates accounts by dataset. Monetary strings are exact; float transforms are used only for ML features. Evidence totals are grouped by currency. Cross-currency sums/FX conversions are not invented. Pass-through compares an intermediate account's received amount with its outgoing paid amount in the same currency. SAML may use paid amount when source and receiving currencies match; this assumes same-currency amount comparability, not proof of settlement or ownership.

Time-axis numeric values support sorting only. Naive source timestamps are not asserted to be UTC. API-created job/audit dates are UTC. Tied minute timestamps cannot establish transfer order and are excluded from strictly ordered chain/cycle steps.

Labels never enter the transactions table or feature vector. AMLSim account labels cannot stand in for transaction labels. Device identifiers are optional evidence; the original three prepared datasets lack them. Dormancy means an observed gap, not a bank-defined status.

## Scaling boundary

Imports stream to disk with indexed queries, but analysis and ML load a selected time window into memory. Default HTTP limits are 250k imported source rows, 100k analysis rows, 100 MB upload, 500 alerts, 300 graph edges, and 50 ML anomalies. Caps are explicit in the UI or response. Cycles are limited to 2–4 hops, 100 candidates per expansion and 200k expansions. Raising limits requires memory/load measurement, not merely changing a constant.

For multi-tenant/large-scale operation: migrate persistence to PostgreSQL, job orchestration to a durable queue, graph windows to a streaming feature store, authentication to OIDC/RBAC, and artifacts to object storage. These are future infrastructure changes, not claimed implemented capabilities.
