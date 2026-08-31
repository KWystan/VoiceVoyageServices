"""Dynamic Modules Service configuration."""
from dataclasses import dataclass, field
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parent


@dataclass
class ModuleServiceConfig:
    """Configuration for the dynamic modules (practice-plan) service."""
    host: str = "0.0.0.0"
    port: int = 8002
    cors_origins: list = field(default_factory=lambda: ["*"])

    # LLM provider: "openrouter" (OpenRouter) | "zen" (OpenCode Zen) | "none" (rule-based only)
    llm_provider: str = "openrouter"
    # Nemotron-3 Ultra (Free) — 1 Million token context window
    # OpenRouter: "nvidia/nemotron-3-ultra-550b-a55b:free" | Zen: "nemotron-3-ultra-free"
    llm_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    zen_base_url: str = "https://opencode.ai/zen/v1"
    api_key_env: str = "OPENROUTER_API_KEY"
    request_timeout_sec: float = 20.0
    max_retries: int = 2  # fast failover to rule-based fallback if LLM throttles

    # Module building
    items_per_level: int = 4
    levels_order: tuple = ("syllable", "word", "phrase", "sentence")

    # Mock data (professional outlines + word bank)
    outlines_path: Path = field(
        default_factory=lambda: _SERVICE_ROOT / "data" / "module_outlines.json")
    word_bank_path: Path = field(
        default_factory=lambda: _SERVICE_ROOT / "data" / "word_bank.json")

    # The static prompt (rules) fed to the LLM
    prompt_path: Path = field(
        default_factory=lambda: _SERVICE_ROOT / "data" / "prompt.md")

    # Grade-level gameplay documents (modular curriculum context).
    # 0 = Kindergarten (Ages 4-5), 1 = Grade 1 (Ages 5-6), 2 = Grade 2 (Ages 6-7), 3 = Grade 3 (Age 8).
    grade_docs: dict = field(default_factory=lambda: {
        0: _SERVICE_ROOT / "data" / "curriculum_kindergarten.md",
        1: _SERVICE_ROOT / "data" / "curriculum_grade_1.md",
        2: _SERVICE_ROOT / "data" / "curriculum_grade_2.md",
        3: _SERVICE_ROOT / "data" / "curriculum_grade_3.md",
    })


# Singleton
config = ModuleServiceConfig()
