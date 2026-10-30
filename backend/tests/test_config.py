import os

import app.config as config


def test_dotenv_loader_sets_missing_vars_only_and_ignores_comments(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nGC_TEST_KEY=\"abc\"\nGC_TEST_NAME = x/y \nEMPTY=\nNOEQUALS\n"
        "GC_TEST_SHELL=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GC_TEST_SHELL", "from-shell")
    for k in ("GC_TEST_KEY", "GC_TEST_NAME", "EMPTY"):
        monkeypatch.delenv(k, raising=False)
    config.load_dotenv([env, tmp_path / "missing.env"])
    assert os.environ["GC_TEST_KEY"] == "abc"  # quotes stripped
    assert os.environ["GC_TEST_NAME"] == "x/y"  # whitespace trimmed
    assert os.environ["GC_TEST_SHELL"] == "from-shell"  # the shell wins over the file
    assert "EMPTY" not in os.environ and "NOEQUALS" not in os.environ
    for k in ("GC_TEST_KEY", "GC_TEST_NAME"):
        os.environ.pop(k, None)


def test_postgres_connections_are_tested_before_use_because_managed_databases_pause():
    import pytest

    pytest.importorskip("psycopg")
    from app.db.session import make_engine

    pg = make_engine("postgresql+psycopg://u:p@localhost:5432/d")
    assert pg.pool._pre_ping is True and pg.pool._recycle == 300
    assert make_engine("sqlite://").pool._pre_ping is False
