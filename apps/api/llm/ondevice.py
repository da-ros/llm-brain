"""On-device Qwen3.5-4B provider (React Native / Neural Engine / Metal).

Free: base model quantized Q4.
Premium: fine-tuned quantized Q4.

Inference runs in the iPhone app, not in this API process. The class exists so
`get_provider()` can resolve `LLM_PROVIDER=ondevice` without code changes.
"""

from __future__ import annotations

from typing import Literal

OnDeviceVariant = Literal["base", "finetuned"]


class OnDeviceProvider:
    """Contract for on-device Qwen3.5-4B Q4 (Neural Engine / Metal)."""

    name = "ondevice"

    def __init__(self, variant: OnDeviceVariant = "base") -> None:
        self.variant = variant
        self.model = "Qwen3.5-4B"
        self.quantization = "Q4"
        self.runtime = "react-native-neural-engine-metal"

    def chat(self, messages: list[dict], context: str | None = None) -> str:
        _ = (messages, context)
        raise RuntimeError(
            "On-device Qwen3.5-4B Q4 inference runs in the React Native iPhone app "
            "(Neural Engine / Metal), not in this API process. "
            "Free uses the base Q4 build; Premium uses the fine-tuned Q4 build."
        )

    def complete(self, prompt: str) -> str:
        _ = prompt
        raise RuntimeError(
            "On-device Qwen3.5-4B Q4 inference runs in the React Native iPhone app "
            "(Neural Engine / Metal), not in this API process."
        )
