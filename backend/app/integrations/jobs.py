"""Benchmark job backends.

Real GPU measurements come from Nebius Serverless Jobs running the `bench/` image. That launch
path has NOT been built: it needs the Nebius account, credentials and the CLI/API details that
the Day-1 spike was meant to confirm, and none of those exist in this repository yet. Rather than
guess at an API, this module reports honestly that jobs are unconfigured.

Until then, measurements enter through (a) the committed replay files, (b) the import endpoints
(bench JSON, nvidia-smi CSV, tegrastats) and (c) manual entry.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class JobsStatus:
    configured: bool
    reason: str


def status() -> JobsStatus:
    needed = ("NEBIUS_PROJECT_ID", "NEBIUS_OBJECT_STORE_BUCKET")
    missing = [k for k in needed if not os.environ.get(k)]
    if missing:
        return JobsStatus(False, f"not configured: set {', '.join(missing)}")
    return JobsStatus(
        False,
        "credentials are set, but the Serverless Jobs launcher has not been implemented; "
        "run bench/ manually and import the JSON result",
    )
