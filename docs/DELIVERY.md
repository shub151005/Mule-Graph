# Agile delivery board

The scope is organized as vertical increments with explicit acceptance gates. Requirements may change without rewriting ingestion, rule logic, ML, and UI together.

| Increment | Scope | Acceptance gate |
| --- | --- | --- |
| 1. Data foundation | Adapters, SQLite, validation, provenance, jobs, API | Import all three schema families without inventing missing values |
| 2. Intelligence | Seven conditional rules, anomaly ML, supervised baseline, evaluation | Evidence references real rows; labels excluded from features; temporal holdout |
| 3. Investigation UX | Six connected pages, graph, filters, dossiers, notes, exports | An analyst can go from dataset to alert to documented evidence |
| 4. Delivery hardening | Automated tests, responsive checks, reproducible build, deployment docs | Tests/build pass; limits and remaining deployment requirements documented |

## Definition of done

No decorative nonfunctional controls, no fabricated statistics, validated API inputs, useful loading/error/empty states, persisted analyst actions, reproducible model cards, source data untouched, deployable configuration, and explicit limitations.

## Change protocol

1. Record the requested change, affected screen/API and acceptance criteria.
2. Keep data semantics fixed unless a migration is explicitly reviewed.
3. Add/adjust the smallest rule, service or component; avoid one-off UI-only fake state.
4. Run regression tests and recheck the complete investigation flow before release.

Deferred infrastructure is listed in ARCHITECTURE.md. Missing source evidence is listed in LIMITATIONS.md; it is never silently replaced with invented data.
