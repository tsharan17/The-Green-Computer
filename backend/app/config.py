from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_url: str = os.environ.get("GC_DB_URL", "sqlite:///./green_computer.db")
    api_prefix: str = "/api/v1"


def get_settings() -> Settings:
    return Settings()
