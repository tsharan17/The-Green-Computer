from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_ENV_LOADED = False


def load_dotenv(paths: list[Path] | None = None) -> None:
    """Load KEY=VALUE lines from `.env` (repo root, then backend/) without overriding variables
    that are already set. Tiny on purpose: no dependency, no interpolation, no secrets logged."""
    global _ENV_LOADED
    if paths is None:
        if _ENV_LOADED:
            return
        _ENV_LOADED = True
        here = Path(__file__).resolve()
        paths = [here.parents[2] / ".env", here.parents[1] / ".env"]
    for candidate in paths:
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    db_url: str
    api_prefix: str = "/api/v1"


def get_settings() -> Settings:
    load_dotenv()
    return Settings(db_url=os.environ.get("GC_DB_URL", "sqlite:///./green_computer.db"))


# --- LLM provider (Nebius Token Factory by default; any OpenAI-compatible endpoint works) -----

# Verified against the Token Factory documentation.
DEFAULT_LLM_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"

# NOT verified: these come from third-party catalogues. The router checks them against the
# provider's own model list at run time and falls back to name matching, so a wrong ID here
# degrades gracefully instead of breaking.
DEFAULT_MODEL_HINTS = {
    "ultra": "nvidia/Nemotron-3-Ultra-550b-a55b",
    "super": "nvidia/nemotron-3-super-120b-a12b",
    "nano": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
}


@dataclass(frozen=True)
class LLMSettings:
    api_key: str | None
    base_url: str
    ultra: str
    super_: str
    nano: str
    timeout_s: float
    max_tool_calls: int

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def get_llm_settings() -> LLMSettings:
    load_dotenv()
    env = os.environ.get
    return LLMSettings(
        api_key=env("TOKEN_FACTORY_API_KEY") or None,
        base_url=(env("TOKEN_FACTORY_BASE_URL") or DEFAULT_LLM_BASE_URL).rstrip("/") + "/",
        ultra=env("GC_MODEL_ULTRA") or DEFAULT_MODEL_HINTS["ultra"],
        super_=env("GC_MODEL_SUPER") or DEFAULT_MODEL_HINTS["super"],
        nano=env("GC_MODEL_NANO") or DEFAULT_MODEL_HINTS["nano"],
        timeout_s=float(env("GC_LLM_TIMEOUT_S") or 120),
        max_tool_calls=int(env("GC_AGENT_MAX_TOOL_CALLS") or 12),
    )
