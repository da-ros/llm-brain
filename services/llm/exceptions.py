"""Domain errors for local Qwen3.5-4B inference."""


class InferenceError(Exception):
    """Base inference failure."""


class ModelUnavailableError(InferenceError):
    """Local Qwen3.5-4B container / runtime is not ready."""


class ModelNotFoundError(InferenceError):
    """Configured Qwen3.5-4B weights are missing."""


class InferenceTimeoutError(InferenceError):
    """Inference exceeded INFERENCE_TIMEOUT_SECONDS."""
