import os

import pytest

# Cheaper password hashing in tests (production default is 2**15 with p=3).
os.environ.setdefault("GC_SCRYPT_LOG2_N", "10")
os.environ.setdefault("GC_SCRYPT_P", "1")

SECRET_VARS = (
    "GC_SMTP_PASSWORD",
    "GC_SENTRY_DSN",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Tests never read a developer's real .env or keys, and never call a live provider."""
    import app.config as config

    monkeypatch.setattr(config, "_ENV_LOADED", True)
    for v in SECRET_VARS:
        monkeypatch.delenv(v, raising=False)


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """The limiter is process-wide; tests sign up many accounts from the same test address."""
    import app.security as sec

    sec.LIMITER.reset()
    yield
    # An app built on a test database may have pointed the shared limiter at it; that database can be
    # gone now, so go back to the in-memory limiter for the next test.
    sec.LIMITER.backend, sec.LIMITER.kind = sec.RateLimiter(), "memory"
