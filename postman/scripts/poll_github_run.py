#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

RUN_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 33690172060
token = os.environ["GITHUB_TOKEN"]
headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def fetch_run() -> dict:
    url = f"https://api.github.com/repos/AM-Portfolio/am-platform/actions/runs/{RUN_ID}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resp:
        return json.loads(resp.read())


for attempt in range(24):
    run = fetch_run()
    print(f"attempt {attempt + 1}: {run['status']} {run.get('conclusion')}")
    if run["status"] == "completed":
        print("head_sha", run["head_sha"])
        sys.exit(0 if run.get("conclusion") == "success" else 1)
    time.sleep(15)
print("timeout")
sys.exit(2)
