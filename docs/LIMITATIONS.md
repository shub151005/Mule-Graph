# Capability and evidence boundaries

Implemented: data ingestion/quality reports; chronological rules; ML training/evaluation; investigator graph and transaction views; account dossiers; analyst notes/status; evidence export; job and audit history.

Conditional: supervised ML needs transaction labels and both classes in every time split; shared-device detection needs supplied device_id; observed dormancy needs dated prior activity and enough history. Original AMLSim supports step-based graphs, not minute-based latency claims. Normal fan-in/out can be false positives.

Not implemented or claimed: live bank feeds, GNNs, identity/KYC enrichment, sanctions lists, account freezing, FinCEN filing, legal case management, verified multi-user identities, calibrated probabilities of fraud, certified regulatory compliance, unlimited graph traversal, automatic FX conversion, or proven real-world accuracy.

These are not hidden features. The screenshot's fictional names, 94.2% confidence, FIPS claim and regulatory buttons are intentionally replaced with genuine research functions.

Model scores are not calibrated fraud probabilities. The IF percentile is relative to training observations. Metrics are scoped to the imported synthetic sample; account overlap across chronological splits is disclosed. Prefix imports can distort prevalence and omit context. Use a separate independent, context-preserving evaluation collection for stronger claims.

The source preparation audit found identical PDF files named `HI-Small_Patterns.txt`, and an AMLSim metadata count of 1,803 versus 1,804 positives in nodes.csv. This build does not silently correct or rewrite those originals.
