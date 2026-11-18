# Corpus

Not inventoried yet.

When it is, `manifest.csv` needs these columns:

`doc_id,format,bytes_or_duration,provenance,anonymized,split,notes`

`split` is `train` or `eval`. The v5 batch
`6af7ffe6805d32e6f8fb9a12.jsonl` (27 records, sha256
`8d5f8f08f93cc24f314fdff196d8fd7cff9a5eb77e4b942a0a39dcb470c00295`)
is `train`. Evaluation queries go in `eval-queries.jsonl` and must not
repeat those records.

Do not commit the personal files. The manifest describes them.
