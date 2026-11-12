"""Configurable model catalog; credentials are supplied separately via environment."""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    name: str
    capabilities: frozenset[str]
    context_window: int
    cost_per_1k: float
    latency_score: float = 1.0


def load_catalog() -> list[ModelConfig]:
    """Parse provider:model:context:cost entries; malformed entries are ignored."""
    raw = os.getenv("MODEL_CATALOG", "openai:gpt-4o-mini:8192:0.0002")
    models = []
    for entry in raw.split(","):
        parts = entry.strip().split(":")
        if len(parts) != 4:
            continue
        provider, name, context, cost = parts
        try:
            window, price = int(context), float(cost)
        except ValueError:
            continue
        if provider not in {"openai", "anthropic", "google"} or window < 1 or price < 0:
            continue
        caps = {"general", "language"}
        if provider in {"openai", "anthropic", "google"}:
            caps.add("reasoning")
        if os.getenv(f"MODEL_{name.upper().replace('-', '_')}_BURMESE", "false").lower() == "true":
            caps.add("burmese")
        models.append(ModelConfig(provider, name, frozenset(caps), window, price))
    return models
