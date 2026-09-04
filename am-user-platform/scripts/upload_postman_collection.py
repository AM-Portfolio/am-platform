"""Upload local collection JSON to Postman workspace. Needs POSTMAN_API_KEY in ~/.asrax/credentials.env."""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request

WORKSPACE = "c1ed9ba4-e485-4377-8374-7685abf4247d"
ROOT = pathlib.Path(__file__).resolve().parents[1] / "postman"
PAYLOAD = ROOT / "_upload_payload.json"
IDS = ROOT / "_postman_ids.json"
ENV_UID = "56761657-3f6f40c7-80f0-4a72-9b6d-344dfeb183c3"


def main() -> None:
    creds: dict[str, str] = {}
    for line in (pathlib.Path.home() / ".asrax" / "credentials.env").read_text(
        encoding="utf-8"
    ).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        creds[k.strip()] = v.strip().strip('"')
    key = creds.get("POSTMAN_API_KEY") or creds.get("POSTMAN_KEY")
    if not key:
        raise SystemExit("FAIL: POSTMAN_API_KEY missing")

    col = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    body = json.dumps({"collection": col}).encode()
    req = urllib.request.Request(
        f"https://api.getpostman.com/collections?workspace={WORKSPACE}",
        data=body,
        headers={"X-Api-Key": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print("FAIL", e.code, e.read().decode(errors="replace")[:400])
        raise SystemExit(1) from e

    c = data.get("collection") or {}
    uid = c.get("uid") or c.get("id")
    print("OK collection", c.get("name"), uid)
    IDS.write_text(
        json.dumps(
            {
                "collection_uid": uid,
                "environment_uid": ENV_UID,
                "workspace": WORKSPACE,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("OK wrote", IDS.name)


if __name__ == "__main__":
    main()
