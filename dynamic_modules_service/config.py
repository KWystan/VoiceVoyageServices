"""Dynamic Modules Service configuration.

Runtime policy is environment-driven so development remains convenient while
production cannot silently inherit permissive CORS or authentication defaults.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parent


def _csv_env(name: str, default: str = "") -> list[str]:
    return [
        value.strip()
        for value in os.environ.get(name, default).split(",")
        if value.strip()
    ]


def _default_provider() -> str:
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if explicit:
        return explicit
    if os.environ.get("ZEN_API_KEY"):
        return "zen"
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    return "none"


def _default_model() -> str:
    configured = os.environ.get("LLM_MODEL", "").strip()
    if configured:
        return configured
    if _default_provider() == "openrouter":
        return "nvidia/nemotron-3-ultra-550b-a55b:free"
    if _default_provider() == "zen":
        return "nemotron-3-ultra-free"
    return "rule-based"


@dataclass
class ModuleServiceConfig:
    """Configuration for the dynamic modules (practice-plan) service."""

    host: str = "0.0.0.0"
    port: int = 8002
    environment: str = field(
        default_factory=lambda: os.environ.get(
            "APP_ENV", "development"
        ).strip().lower()
    )
    cors_origins: list[str] = field(
        default_factory=lambda: _csv_env(
            "CORS_ORIGINS", "http://127.0.0.1,http://localhost"
        )
    )

    # Authentication is optional locally. Production must explicitly use
    # Firebase ID tokens or a service-to-service bearer token.
    auth_mode: str = field(
        default_factory=lambda: os.environ.get(
            "VV_AUTH_MODE", "off"
        ).strip().lower()
    )
    api_token_env: str = "VV_API_TOKEN"
    max_processes_json_bytes: int = field(
        default_factory=lambda: int(
            os.environ.get("MAX_PROCESSES_JSON_BYTES", "16384")
        )
    )
    max_detected_processes: int = 24

    # LLM provider: none | zen | openrouter. With no explicit provider, a
    # configured key selects its matching provider; otherwise rule-based mode.
    llm_provider: str = field(default_factory=_default_provider)
    llm_model: str = field(default_factory=_default_model)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    zen_base_url: str = "https://opencode.ai/zen/v1"
    request_timeout_sec: float = field(
        default_factory=lambda: float(os.environ.get("LLM_TIMEOUT_SEC", "90"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.environ.get("LLM_MAX_RETRIES", "4"))
    )

    # Module building.
    items_per_level: int = 4
    max_candidate_outlines: int = 3
    levels_order: tuple[str, ...] = (
        "syllable",
        "word",
        "phrase",
        "sentence",
    )

    outlines_path: Path = field(
        default_factory=lambda: _SERVICE_ROOT / "data" / "module_outlines.json"
    )
    word_bank_path: Path = field(
        default_factory=lambda: _SERVICE_ROOT / "data" / "word_bank.json"
    )
    prompt_path: Path = field(
        default_factory=lambda: _SERVICE_ROOT / "data" / "prompt.md"
    )

    # Human-readable source documents. They are not sent wholesale to the LLM.
    grade_docs: dict[int, Path] = field(
        default_factory=lambda: {
            0: _SERVICE_ROOT / "data" / "curriculum_kindergarten.md",
            1: _SERVICE_ROOT / "data" / "curriculum_grade_1.md",
            2: _SERVICE_ROOT / "data" / "curriculum_grade_2.md",
            3: _SERVICE_ROOT / "data" / "curriculum_grade_3.md",
        }
    )

    @property
    def is_production(self) -> bool:
        return self.environment in {"production", "prod"}

    @property
    def llm_base_url(self) -> str:
        return (
            self.openrouter_base_url
            if self.llm_provider == "openrouter"
            else self.zen_base_url
        )

    @property
    def llm_api_key_env(self) -> str:
        return (
            "OPENROUTER_API_KEY"
            if self.llm_provider == "openrouter"
            else "ZEN_API_KEY"
        )

    def validate_runtime(self) -> None:
        if self.llm_provider not in {"none", "zen", "openrouter"}:
            raise RuntimeError(
                "LLM_PROVIDER must be one of: none, zen, openrouter"
            )
        if self.auth_mode not in {"off", "firebase", "token"}:
            raise RuntimeError(
                "VV_AUTH_MODE must be one of: off, firebase, token"
            )
        if "*" in self.cors_origins:
            raise RuntimeError("Wildcard CORS origins are not permitted")
        if self.is_production and any(
            not origin.startswith("https://") for origin in self.cors_origins
        ):
            raise RuntimeError("Production CORS origins must use HTTPS")
        if self.is_production and self.auth_mode not in {"firebase", "token"}:
            raise RuntimeError(
                "Production requires VV_AUTH_MODE=firebase or VV_AUTH_MODE=token"
            )
        if self.auth_mode == "token" and not os.environ.get(self.api_token_env):
            raise RuntimeError(
                f"{self.api_token_env} must be set when VV_AUTH_MODE=token"
            )


config = ModuleServiceConfig()
