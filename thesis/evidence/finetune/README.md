# Fine-tune evidence

Account `57eec20b-9ee6-4e75-bc87-1668a8e5f8b6` (Nora Vega). The pipeline
writes every completed job onto `data/models/{user_id}/adapter/`, so the
directory on disk is the last successful job. The definitive adapter for
the alpha round is **v5**, which is also the tag on the exported phone pack.

These five logs are real. The dataset path is the path the agents service
stored (`/app/data/...`). The host process on port 8004 reads that batch
from the repository `data/` directory. The September 2026 logs for `user1`
under pytest temporary paths are mock and are not copied here.

| Version | Job | Completed (UTC) | Triples | Epochs | Final loss | Loss target |
|---------|-----|-----------------|---------|--------|------------|-------------|
| v1 | `ft-job-3bbf9941` | 2026-11-12T02:06:16 | 29 | 3 | 1.6419 | — |
| v2 | `ft-job-c0ca6047` | 2026-11-12T21:09:27 | 29 | 3 | 0.147 | 0.3 |
| v3 | `ft-job-99e0f689` | 2026-11-12T22:29:18 | 33 | 7 | 0.0471 | 0.05 |
| v4 | `ft-job-9fd6dfad` | 2026-11-13T06:26:10 | 29 | 7 | 0.0349 | 0.05 |
| v5 | `ft-job-56f3ab60` | 2026-11-16T21:43:47 | 27 | 8 | 0.0082 | 0.05 |

Shared hyperparameters on these jobs: PEFT, base `qwen3.5-4b`, LoRA rank 16,
learning rate 0.0002, max epochs 30, max training time 2 hours. v5 ran for
0.0566 hours.

## v5 batch

- Path: `data/finetune_batches/57eec20b-9ee6-4e75-bc87-1668a8e5f8b6/6af7ffe6805d32e6f8fb9a12.jsonl`
- Records: 27
- Bytes: 10560
- SHA-256: `8d5f8f08f93cc24f314fdff196d8fd7cff9a5eb77e4b942a0a39dcb470c00295`
- The file stays in `data/`. It is training data, not the evaluation set.

## v5 phone pack

`pack-manifest.json` is a copy of
`data/on-device/users/57eec20b-9ee6-4e75-bc87-1668a8e5f8b6/manifest.json`.

- Tag: `qwen3.5-4b-lora-v5`
- File: `qwen3.5-4b-finetuned-q4.gguf`
- Bytes: 2708804096
- SHA-256: `2110d3cc8c0db8e17b8f0e259a47f220dae9583f89bec6502b752c0738d6a81d`

The GGUF is not in this directory. This round does not time the phone pack.

## How to read the loss

Final loss is the training loss on that job's triples. v5 reaching 0.0082
on 27 triples is not a held-out score. The laptop reproduction check is the
`adapter-v5` rows in `thesis/evidence/runs/generation.jsonl`.
