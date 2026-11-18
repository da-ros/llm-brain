"""Answer the evaluation questions with the v5 adapter on this Mac.

The server on port 8003 keeps the base checkpoint. This process loads
Qwen3.5-4B and the Nora Vega adapter itself, with no retrieved context.
The prompt is the training prefix: instruction, question, and an empty
think block already closed. Stop the server on port 8003 before running
this, so two copies of the checkpoint are not resident together.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "data/models/57eec20b-9ee6-4e75-bc87-1668a8e5f8b6/adapter"
QUERIES = Path(__file__).resolve().parent / "corpus/eval-queries.jsonl"
OUT = Path(__file__).resolve().parent / "runs/generation.jsonl"
USER_ID = "57eec20b-9ee6-4e75-bc87-1668a8e5f8b6"
INSTRUCTION = (
    "When the question is about this person's record, answer with that fact. "
    "For any other question, answer normally."
)


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _load_lora():
    spec = importlib.util.spec_from_file_location(
        "finetune_lora", ROOT / "services/finetune/lora.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["finetune_lora"] = module
    spec.loader.exec_module(module)
    return module


def _install_mps_fallback() -> None:
    sys.path.insert(0, str(ROOT / "services/llm"))
    from providers.qwen_local import _install_mps_convolution_fallback

    _install_mps_convolution_fallback()


def main() -> None:
    if _port_open(8003):
        raise SystemExit("port 8003 is open; stop the host LLM before this probe")
    source = (ROOT / "services/finetune/pipeline.py").read_text(encoding="utf-8")
    if "answer with that fact." not in source or "answer normally." not in source:
        raise SystemExit("training instruction text no longer matches pipeline.py")
    lora = _load_lora()
    import os

    os.environ.setdefault("HF_HOME", str(ROOT / "data/huggingface"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(ROOT / "data/huggingface/hub"))
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration

    _install_mps_fallback()
    if not torch.backends.mps.is_available():
        raise SystemExit("this probe needs Metal")
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3.5-4B", local_files_only=True)
    base = Qwen3_5ForConditionalGeneration.from_pretrained(
        "Qwen/Qwen3.5-4B",
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        local_files_only=True,
    )
    model = PeftModel.from_pretrained(base, str(ADAPTER))
    model.to("mps").eval()
    stop_id = tokenizer.convert_tokens_to_ids("<|im_end|>")

    queries = [
        json.loads(line)
        for line in QUERIES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    done = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("config") == "adapter-v5" and row.get("path") == "host-probe":
                done.add((row["query_id"], row.get("repetition", 1)))
    with OUT.open("a", encoding="utf-8") as handle:
        for repetition in (2, 3):
            for query in queries:
                if (query["query_id"], repetition) in done:
                    continue
                prefix = lora.chat_prompt(INSTRUCTION, query["question"]) + lora.THINK_CLOSE
                started = time.perf_counter()
                encoded = tokenizer(prefix, return_tensors="pt")
                encoded = {key: value.to("mps") for key, value in encoded.items()}
                with torch.inference_mode():
                    generated = model.generate(
                        **encoded,
                        max_new_tokens=256,
                        do_sample=False,
                        eos_token_id=stop_id,
                    )
                new_tokens = generated[0, encoded["input_ids"].shape[1] :]
                text = tokenizer.decode(new_tokens, skip_special_tokens=False)
                if "<|im_end|>" in text:
                    text = text.split("<|im_end|>", 1)[0]
                text = text.strip()
                total_ms = int((time.perf_counter() - started) * 1000)
                row = {
                    "config": "adapter-v5",
                    "query_id": query["query_id"],
                    "repetition": repetition,
                    "total_ms": total_ms,
                    "response": text,
                    "source_ids": [],
                    "expected_answer": query["expected_answer"],
                    "relevant_ids": query["relevant_ids"],
                    "training_relation": query["training_relation"],
                    "in_grounding_kpi": False,
                    "path": "host-probe",
                    "prompt": "training-prefix",
                    "user_id": USER_ID,
                    "kind": "real",
                    "note": "No retrieved context. Reproduction of the v5 answers, not a held-out exam.",
                }
                handle.write(json.dumps(row) + "\n")
                handle.flush()
                print(f"adapter-v5 {query['query_id']} rep {repetition} {total_ms} ms")


if __name__ == "__main__":
    main()
