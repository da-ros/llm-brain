"""Local LoRA backends over Qwen3.5-4B (PEFT / ms-swift / Unsloth).

Mock mode writes an adapter stub so CI and laptop demos do not need a GPU.
Real backends run when LORA_MOCK=false and the extra packages are installed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, sleep
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Settings

SUPPORTED_BACKENDS = ("peft", "ms-swift", "unsloth")


@dataclass(frozen=True)
class TrainingMetrics:
    """Metrics recorded at the end of a LoRA job."""

    epochs: int
    final_loss: float
    training_time_hours: float
    backend: str


def write_adapter_stub(adapter_dir: Path, *, base_model_id: str, backend: str) -> None:
    """Persist a LoRA adapter directory (stub weights + config)."""
    adapter_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "base_model_name_or_path": base_model_id,
        "peft_type": "LORA",
        "r": 8,
        "lora_alpha": 16,
        "lora_dropout": 0.05,
        "target_modules": ["q_proj", "v_proj"],
        "backend": backend,
        "task_type": "CAUSAL_LM",
    }
    (adapter_dir / "adapter_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (adapter_dir / "adapter_model.bin").write_bytes(b"LORA-ADAPTER-STUB")
    (adapter_dir / "README.md").write_text(
        "LoRA adapter for Premium on-device build (Frame 10).\n"
        "Cloud LLM container stays base Qwen3.5-4B (not fine-tuned).\n",
        encoding="utf-8",
    )


def run_lora_training(
    *,
    examples: list[dict],
    adapter_dir: Path,
    settings: Settings,
    delay_seconds: float | None = None,
) -> TrainingMetrics:
    """Run local LoRA over Qwen3.5-4B and return metrics."""
    backend = settings.LORA_BACKEND.lower()
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(f"Unsupported LoRA backend: {settings.LORA_BACKEND}")

    started = perf_counter()
    if settings.LORA_MOCK:
        sleep(delay_seconds if delay_seconds is not None else settings.LORA_MOCK_DELAY_SECONDS)
        write_adapter_stub(adapter_dir, base_model_id=settings.BASE_MODEL_ID, backend=backend)
        elapsed_hours = (perf_counter() - started) / 3600.0
        # Deterministic mock loss that improves with more examples / epochs.
        n = max(1, len(examples))
        final_loss = round(max(0.05, 0.4 - 0.01 * n - 0.02 * settings.TRAINING_EPOCHS), 4)
        return TrainingMetrics(
            epochs=settings.TRAINING_EPOCHS,
            final_loss=final_loss,
            training_time_hours=round(elapsed_hours, 6),
            backend=backend,
        )

    if backend == "peft":
        return _run_peft(examples, adapter_dir, settings, started)
    if backend == "unsloth":
        return _run_unsloth(examples, adapter_dir, settings, started)
    return _run_ms_swift(examples, adapter_dir, settings, started)


def _train_device() -> str:
    """Metal on this Mac, CUDA on a GPU machine. CPU cannot run this checkpoint."""
    import torch

    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    raise RuntimeError("Qwen3.5-4B LoRA needs Metal or CUDA. This process has neither.")


def _prepare_local_weights() -> None:
    """Use the checkpoint already stored under data/huggingface."""
    root = Path(__file__).resolve().parents[2]
    home = Path(os.environ.get("HF_HOME", root / "data" / "huggingface"))
    os.environ.setdefault("HF_HOME", str(home))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(home / "hub"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


def _run_peft(
    examples: list[dict],
    adapter_dir: Path,
    settings: Settings,
    started: float,
) -> TrainingMetrics:
    """LoRA over the local Qwen3.5-4B checkpoint. The loss is on the answer."""
    try:
        import torch
        from peft import LoraConfig, get_peft_model
        from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
    except ImportError as exc:
        raise RuntimeError(
            "PEFT backend requires peft, transformers, and torch. "
            "Install services/finetune/requirements-gpu.txt or set LORA_MOCK=true."
        ) from exc

    _prepare_local_weights()
    device = _train_device()
    model_id = settings.QWEN_HF_MODEL_ID or "Qwen/Qwen3.5-4B"
    tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = Qwen3_5ForConditionalGeneration.from_pretrained(
        model_id,
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        local_files_only=True,
    )
    model = get_peft_model(
        model,
        LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "v_proj"],
        ),
    )
    model.to(device)
    model.train()
    optimizer = torch.optim.AdamW(
        (param for param in model.parameters() if param.requires_grad),
        lr=settings.TRAINING_LR,
    )
    losses: list[float] = []
    for _epoch in range(settings.TRAINING_EPOCHS):
        for example in examples:
            prompt = f"{example['instruction']}\n{example['input']}\n"
            full = prompt + str(example["output"])
            encoded = tokenizer(full, return_tensors="pt", truncation=True, max_length=512)
            prompt_ids = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
            labels = encoded["input_ids"].clone()
            prompt_len = min(prompt_ids["input_ids"].shape[1], labels.shape[1])
            labels[:, :prompt_len] = -100
            encoded = {key: value.to(device) for key, value in encoded.items()}
            labels = labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = model(**encoded, labels=labels).loss
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().float().cpu()))
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    elapsed_hours = (perf_counter() - started) / 3600.0
    final = sum(losses) / len(losses) if losses else 0.0
    return TrainingMetrics(
        epochs=settings.TRAINING_EPOCHS,
        final_loss=round(final, 4),
        training_time_hours=round(elapsed_hours, 4),
        backend="peft",
    )


def _run_unsloth(examples, adapter_dir, settings, started) -> TrainingMetrics:
    try:
        import unsloth  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Unsloth backend requires the unsloth package. Set LORA_MOCK=true for CI."
        ) from exc
    return _run_peft(examples, adapter_dir, settings, started)


def _run_ms_swift(examples, adapter_dir, settings, started) -> TrainingMetrics:
    try:
        import ms_swift  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "ms-swift backend requires the ms-swift package. Set LORA_MOCK=true for CI."
        ) from exc
    return _run_peft(examples, adapter_dir, settings, started)
