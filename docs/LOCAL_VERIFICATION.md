# Local development verification — 23 September 2026

## Engineering checks

- 24 backend regression tests pass. Two third-party deprecation warnings remain in Starlette's test client; no failing assertions.
- Two browser end-to-end scenarios pass: investigation/notes/status/CSV export/graph/model screens/responsive navigation, and upload/job completion/analysis/source switching.
- TypeScript and Vite production build pass. Graph code is split into a separate bundle; no chunk-size warning remains.
- `pip check` reports no broken requirements; npm installation audit reported zero known vulnerabilities at installation time (not a security certification).
- Desktop and 390px-wide mobile screens were rendered and visually inspected. Captures are local in `runtime/` (not committed).

## Original-source checks

Each source was imported into a new application collection without modifying the original CSVs:

| Source | Rows imported | Rejections | Labels observed |
| --- | --- | --- | --- |
| IBM | 5,000 | 0 | 4,999 normal / 1 positive transaction |
| SAML | 5,000 | 0 | 4,991 normal / 9 positive transactions |
| AMLSim | 5,000 | 0 | 6,251 normal / 691 positive involved accounts |

These are source-row prefixes, not representative benchmark samples. AMLSim account counts are not transaction counts.

## Larger development benchmark

A separate 100,000-row SAML prefix imported with zero rejections and 114 positive transaction labels. The model split is 70,000 train / 15,000 validation / 15,000 test. The test period has only 19 positive examples.

Latest supervised baseline (`1b9a140692954004`): Random Forest with exact validation-only F1 threshold selection. Test precision/recall/F1 are all 0 at that threshold; PR-AUC is approximately 0.02468. The Isolation Forest detects 2 of 19 positives with 352 false positives (precision ~0.56%, recall ~10.53%). These results are poor and are shown honestly in the model card. They do not support an effective fraud-detection claim.

The rule engine generated 3,005 candidates and retained its 500 highest heuristic priorities. None of the retained alert transactions matched positive source labels in this prefix. Graph-pattern discovery is functional, but these default thresholds are not a validated laundering classifier. The illustrative sandbox intentionally contains clear pattern examples; its high supervised scores do not generalize to the source benchmark.

## Fixes found during verification

- Alert retention originally favored the first 500 candidates; now it ranks across the complete selected window so later high-priority patterns are not starved.
- CLI database initialization no longer marks another process's active jobs as interrupted; recovery happens only at API startup.
- Equal-timestamp feature extraction uses only earlier timestamps, preventing accidental ordering leakage.
- Graph cycles use a readable circular layout rather than overlapping collinear return edges.
- Dataset switching guards against stale cross-dataset alert requests.
- Threshold selection uses all distinct validation scores, not coarse quantiles that can miss a 0.1% positive tail.

## Next development priorities

1. Investigate pattern time scales and negative lookalikes using training data only; add behavioral rolling features and stable currency context.
2. Define a context-preserving evaluation collection with more positive examples and reserve a new blind final holdout before tuning further.
3. Add analyst review-budget metrics such as precision@K alongside PR-AUC, not an accuracy headline.
4. Continue local user acceptance and refine workflow/graph density from actual use.

Deployment has not been performed. Application workflow readiness and detector-quality readiness are explicitly separate.

## Manual server lifecycle correction

The earlier testing session left detached local server processes, and the first `start-local.ps1` version also used hidden background launches. Ctrl+C in an unrelated VS Code terminal could not stop those processes. Those processes have now been identified by project-specific command lines and stopped; the original data and saved investigations were not deleted.

The launcher now requires an explicit `backend` or `frontend` selection, runs one server in the calling terminal, and streams logs directly there. With no selection it prints help and starts nothing. No `Start-Process`, hidden window, detached job, or automatic browser launch is used. Backend reload is opt-in; frontend port selection is strict rather than silently starting on an alternate port.

Verified in actual foreground terminals: start backend → send Ctrl+C → Uvicorn reports shutdown completed; start frontend → send Ctrl+C → process exits. A final process/port check confirmed ports 8000 and 5173 were free and no project-specific Uvicorn, Vite, or esbuild service process remained. No MuleGraph startup command or scheduled task was found. Both servers were intentionally left stopped.
