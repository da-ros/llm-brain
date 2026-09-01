"""LLM Provider Resolver.

Selects the appropriate LLM provider based on subscription tier.
The backend only uses AWS Bedrock (premium tier).
On-device inference (llama.rn) runs on the mobile app, not the backend.
"""

from services.llm.providers.base import LLMProvider
from services.llm.providers.bedrock import BedrockProvider
from services.llm.config import settings


def get_provider(tier: str = "premium") -> LLMProvider:
    """Get the appropriate LLM provider based on subscription tier.

    Args:
        tier: Subscription tier ("premium" only for backend)

    Returns:
        The appropriate LLM provider

    Raises:
        ValueError: If the tier is not supported
    """
    if tier == "premium":
        return BedrockProvider(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_region=settings.AWS_REGION,
            model_id=settings.BEDROCK_MODEL_ID,
        )
    else:
        raise ValueError(
            f"Unsupported subscription tier: {tier}. "
            f"Backend only supports 'premium' tier. "
            f"Free tier uses on-device llama.rn on mobile."
        )