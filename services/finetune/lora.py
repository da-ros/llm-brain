"""Local LoRA backends over Qwen3.5-4B (PEFT / ms-swift / Unsloth).

Mock mode writes an adapter stub so CI and laptop demos do not need a GPU.
Real backends run when LORA_MOCK=false and the extra packages are installed.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, sleep
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger("finetune-service")

SUPPORTED_BACKENDS = ("peft", "ms-swift", "unsloth")
# Attention, the linear-attention input projections, and the feed-forward layers.
LORA_TARGETS = (
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "in_proj_qkv",
    "in_proj_a",
    "in_proj_b",
    "in_proj_z",
    "gate_proj",
    "up_proj",
    "down_proj",
)


# Shown to the model so the answer follows a closed think block. Not part of the loss.
THINK_CLOSE = "</think>\n\n"


def chat_prompt(instruction: str, question: str) -> str:
    """Qwen3.5 chat turn with the think block left open.

    The phone sends this same string, so a question can write its own thought.
    Training does not score anything inside that block.
    """
    return (
        "<|im_start|>system\n"
        f"{instruction}<|im_end|>\n"
        "<|im_start|>user\n"
        f"{question}<|im_end|>\n"
        "<|im_start|>assistant\n"
        "<think>\n"
    )


def trained_reply(answer: str, end: str = "<|im_end|>") -> str:
    """The answer and the stop token. The think block is left out of the loss."""
    text = answer.strip()
    if text.endswith(end):
        text = text[: -len(end)].rstrip()
    return f"{text}{end}"


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
    on_epoch=None,
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
        return _run_peft(examples, adapter_dir, settings, started, on_epoch)
    if backend == "unsloth":
        return _run_unsloth(examples, adapter_dir, settings, started, on_epoch)
    return _run_ms_swift(examples, adapter_dir, settings, started, on_epoch)


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
    on_epoch=None,
) -> TrainingMetrics:
    """LoRA over the local Qwen3.5-4B checkpoint.

    The loss covers the answer and the stop token. The think block is context.
    """
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
            r=settings.LORA_RANK,
            lora_alpha=settings.LORA_ALPHA,
            lora_dropout=0.05,
            task_type="CAUSAL_LM",
            target_modules=list(LORA_TARGETS),
        ),
    )
    model.to(device)
    model.train()
    optimizer = torch.optim.AdamW(
        (param for param in model.parameters() if param.requires_grad),
        lr=settings.TRAINING_LR,
    )
    end = tokenizer.eos_token or "<|im_end|>"
    epochs_run = 0
    last_mean = 0.0
    for epoch in range(1, settings.TRAIN_MAX_EPOCHS + 1):
        step_losses: list[float] = []
        for example in examples:
            prompt = chat_prompt(str(example["instruction"]), str(example["input"]))
            prefix = prompt + THINK_CLOSE
            full = prefix + trained_reply(str(example["output"]), end)
            encoded = tokenizer(full, return_tensors="pt", truncation=True, max_length=768)
            prefix_ids = tokenizer(prefix, return_tensors="pt", truncation=True, max_length=768)
            labels = encoded["input_ids"].clone()
            prefix_len = min(prefix_ids["input_ids"].shape[1], labels.shape[1])
            labels[:, :prefix_len] = -100
            encoded = {key: value.to(device) for key, value in encoded.items()}
            labels = labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = model(**encoded, labels=labels).loss
            loss.backward()
            optimizer.step()
            step_losses.append(float(loss.detach().float().cpu()))
        epochs_run = epoch
        last_mean = sum(step_losses) / len(step_losses) if step_losses else 0.0
        logger.info(
            "LoRA epoch %s/%s loss %.4f target %.2f",
            epoch,
            settings.TRAIN_MAX_EPOCHS,
            last_mean,
            settings.TRAIN_LOSS_TARGET,
        )
        if on_epoch is not None:
            on_epoch(epoch, last_mean)
        if last_mean < settings.TRAIN_LOSS_TARGET:
            break
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    elapsed_hours = (perf_counter() - started) / 3600.0
    return TrainingMetrics(
        epochs=epochs_run,
        final_loss=round(last_mean, 4),
        training_time_hours=round(elapsed_hours, 4),
        backend="peft",
    )


def _run_unsloth(examples, adapter_dir, settings, started, on_epoch=None) -> TrainingMetrics:
    try:
        import unsloth  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Unsloth backend requires the unsloth package. Set LORA_MOCK=true for CI."
        ) from exc
    return _run_peft(examples, adapter_dir, settings, started, on_epoch)


def _run_ms_swift(examples, adapter_dir, settings, started, on_epoch=None) -> TrainingMetrics:
    try:
        import ms_swift  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "ms-swift backend requires the ms-swift package. Set LORA_MOCK=true for CI."
        ) from exc
    return _run_peft(examples, adapter_dir, settings, started, on_epoch)
