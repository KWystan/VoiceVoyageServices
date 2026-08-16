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

    # LLM provider: "none" (rule-based only) | "zen" (OpenCode Zen)
    llm_provider: str = "zen"
    # deepseek-v4-flash-free is currently throttled provider-side; hy3-free
    # and laguna-s-2.1-free are working free-tier models.
    llm_model: str = "hy3-free"
    zen_base_url: str = "https://opencode.ai/zen/v1"
    api_key_env: str = "ZEN_API_KEY"
    request_timeout_sec: float = 60.0
    max_retries: int = 4  # free tier is rate-limited; retry patiently before falling back

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

    # Grade-level gameplay documents (LLM context, replacing the old CSVs).
    # Each is the full Markdown of the grade's islands/levels/gameplay.
    grade_docs: dict = field(default_factory=lambda: {
        1: _SERVICE_ROOT / "data" / "Grade 1 Game Levels and Gameplay Mechanics.md",
        2: _SERVICE_ROOT / "data" / "Grade_2_Age_6-7_Levels_and_Gameplay.md",
        3: _SERVICE_ROOT / "data" / "Grade_3_Age_8_Levels_and_Gameplay.md",
    })


# Singleton
config = ModuleServiceConfig()
