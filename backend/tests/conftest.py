import pytest

SECRET_VARS = (
    "TOKEN_FACTORY_API_KEY",
    "TOKEN_FACTORY_BASE_URL",
    "GC_MODEL_ULTRA",
    "GC_MODEL_SUPER",
    "GC_MODEL_NANO",
    "NEBIUS_PROJECT_ID",
    "GC_NEBIUS_PLATFORM_OVERRIDE",
    "GC_NEBIUS_PRESET_OVERRIDE",
    "GC_BENCH_IMAGE",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Tests never read a developer's real .env or keys, and never call a live provider."""
    import app.config as config

    monkeypatch.setattr(config, "_ENV_LOADED", True)
    for v in SECRET_VARS:
        monkeypatch.delenv(v, raising=False)
