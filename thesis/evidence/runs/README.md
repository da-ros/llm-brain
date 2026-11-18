# Measurement runs

Rows are real measurements from this laptop round. Three replies per prompt.

Add one JSONL file per family when the run exists:

| File | Row fields |
|------|------------|
| `ingest.jsonl` | correlation_id, format, status, triple_count, error, kind |
| `retrieval.jsonl` | query_id, ranked_ids, list_length, relevant_at_3, kind |
| `generation.jsonl` | config, query_id, total_ms, fact_match, grounded, source_ids, kind |
| `shield.jsonl` | example_id, expected, predicted, match, kind |
| `analytics.jsonl` | series, expected_r, returned_r, kind |
| `simulator.jsonl` | simulation_id, question, variables, scenarios, sources, kind |

`grounded` is true only for `base-rag` when `fact_match` is true and a cited
filename is in `relevant_ids`. Exact copies of a v5 training sentence have
`in_precision_at_3` and `in_grounding_kpi` set false. The means in
`acceptance-matrix.csv` use those flags.

`config` is `base`, `base-rag`, or `adapter-v5`. `kind` is `real` or `mock`.
`total_ms` is the complete reply. This round does not record first-token latency.
