"""Evaluate one project and fail when it is predicted to miss. A prediction, not a measurement."""

import json
import os
import sys
import urllib.error
import urllib.request

headers = {"Authorization": f"Bearer {os.environ['GC_TOKEN']}", "Content-Type": "application/json", "X-GC-CSRF": "1"}
if os.environ.get("GC_WORKSPACE"):
    headers["X-GC-Workspace"] = os.environ["GC_WORKSPACE"]
url = f"{os.environ['GC_URL'].rstrip('/')}/api/v1/projects/{os.environ['GC_PROJECT']}/evaluate"
req = urllib.request.Request(url, data=b"", headers=headers, method="POST")
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        res = json.load(r)
except urllib.error.HTTPError as e:
    sys.exit(f"The server answered {e.code}: {e.read().decode()[:300]}")
for c in res["checks"]:
    print(c)
state = res["feasibility"]
print(f"Verdict (predicted): {state.replace('_', ' ')}")
if state in ("infeasible", "verified_infeasible"):
    sys.exit(1)
