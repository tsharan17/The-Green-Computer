"""Load the built-in device and model libraries from YAML (kept out of the pure engine)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.schemas.hardware import HardwareProfile
from app.schemas.model import ModelProfile

DATA_DIR = Path(__file__).parent / "data"


@lru_cache(maxsize=1)
def load_devices() -> dict[str, HardwareProfile]:
    out: dict[str, HardwareProfile] = {}
    for f in sorted((DATA_DIR / "devices").glob("*.yaml")):
        d = HardwareProfile.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
        out[d.id] = d
    return out


@lru_cache(maxsize=1)
def load_models() -> dict[str, ModelProfile]:
    out: dict[str, ModelProfile] = {}
    for f in sorted((DATA_DIR / "models").glob("*.yaml")):
        m = ModelProfile.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
        out[m.id] = m
    return out


def get_device(device_id: str) -> HardwareProfile:
    try:
        return load_devices()[device_id]
    except KeyError:
        raise KeyError(f"unknown device '{device_id}'") from None


def get_model(model_id: str) -> ModelProfile:
    try:
        return load_models()[model_id]
    except KeyError:
        raise KeyError(f"unknown model '{model_id}'") from None
