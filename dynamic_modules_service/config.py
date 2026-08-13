"""Dynamic Modules Service configuration."""
from dataclasses import dataclass, field
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parent


@dataclass
class ModuleServiceConfig:
    """Configuration for the dynamic modules (practice-plan) service."""
    port: int = 8002

    # LLM provider: "none" (rule-based only) | "zen" (OpenCode Zen)
    llm_provider: str = "zen"
    llm_model: str = "deepseek-v4-flash-free"
    zen_base_url: str = "https://opencode.ai/zen/v1"
    api_key_env: str = "ZEN_API_KEY"
    request_timeout_sec: float = 30.0

    # Module building
    items_per_level: int = 4
    levels_order: tuple = ("syllable", "word", "phrase", "sentence")

    # Mock data (professional outlines + word bank)
    outlines_path: Path = field(
        default_factory=lambda: _SERVICE_ROOT / "data" / "module_outlines.json")
    word_bank_path: Path = field(
        default_factory=lambda: _SERVICE_ROOT / "data" / "word_bank.json")


# Singleton
config = ModuleServiceConfig()
