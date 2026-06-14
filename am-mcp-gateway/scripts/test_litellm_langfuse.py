#!/usr/bin/env python3
"""
Direct integration check for MCP gateway dependencies — no gateway, no auth.

  1. LiteLLM  → POST {LITELLM_BASE_URL}/chat/completions
  2. Langfuse → SDK trace + optional read-back via public API

Loads am-mcp-gateway/.env.preprod by default.

Usage:
  python scripts/test_litellm_langfuse.py
  python scripts/test_litellm_langfuse.py --prompt "What is 2+2?"
  python scripts/test_litellm_langfuse.py --env-file .env.preprod --skip-langfuse-verify
"""
from __future__ import annotations

import argparse
import base64
import sys
import time
import uuid
from pathlib import Path

import httpx
import requests

ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def test_litellm(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    timeout: float,
) -> tuple[str, float]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 64,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"\n[LiteLLM] POST {url}")
    print(f"[LiteLLM] model={model}")

    started = time.perf_counter()
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=payload)
    latency = time.perf_counter() - started

    if response.status_code != 200:
        raise RuntimeError(f"LiteLLM failed [{response.status_code}]: {response.text[:500]}")

    data = response.json()
    answer = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    print(f"[LiteLLM] OK ({latency:.2f}s) tokens={usage}")
    print(f"[LiteLLM] response: {answer[:300]}")
    return answer, latency, usage


def send_langfuse_trace(
    *,
    host: str,
    public_key: str,
    secret_key: str,
    trace_id: str,
    prompt: str,
    response: str,
    model: str,
    latency: float,
    usage: dict[str, int] | None = None,
) -> None:
    """Send trace via Langfuse public ingestion API (no SDK version coupling)."""
    from datetime import datetime, timezone

    url = f"{host.rstrip('/')}/api/public/ingestion"
    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
    }
    now = datetime.now(timezone.utc).isoformat()
    generation_id = str(uuid.uuid4())
    generation_body: dict = {
        "id": generation_id,
        "traceId": trace_id,
        "name": "llm-call",
        "model": model,
        "input": {"message": prompt, "model": model},
        "output": response,
        "metadata": {"latency_seconds": round(latency, 3), "source": "direct-litellm-test"},
    }
    if usage:
        generation_body["usageDetails"] = {
            "input": usage.get("prompt_tokens"),
            "output": usage.get("completion_tokens"),
            "total": usage.get("total_tokens"),
        }

    trace_body: dict = {
        "id": trace_id,
        "name": "mcp-gateway-direct-test",
        "userId": "local-test-user",
        "sessionId": f"test-{trace_id[:8]}",
        "input": {"message": prompt, "model": model},
        "output": response,
        "metadata": {
            "source": "scripts/test_litellm_langfuse.py",
            "model": model,
            "latency_seconds": round(latency, 3),
        },
    }

    batch = [
        {
            "id": str(uuid.uuid4()),
            "type": "trace-create",
            "timestamp": now,
            "body": trace_body,
        },
        {
            "id": str(uuid.uuid4()),
            "type": "generation-create",
            "timestamp": now,
            "body": generation_body,
        },
    ]

    print(f"\n[Langfuse] POST {url}")
    print(f"[Langfuse] trace_id={trace_id}")

    resp = requests.post(url, headers=headers, json={"batch": batch}, timeout=30)
    if resp.status_code not in (200, 207):
        raise RuntimeError(f"Langfuse ingestion failed [{resp.status_code}]: {resp.text[:500]}")

    body = resp.json()
    errors = body.get("errors") or []
    if errors:
        raise RuntimeError(f"Langfuse ingestion batch errors: {errors[:3]}")

    print(f"[Langfuse] ingestion OK ({resp.status_code}, events={len(body.get('successes', []))})")


def verify_langfuse_trace(
    *,
    host: str,
    public_key: str,
    secret_key: str,
    trace_id: str,
    retries: int = 6,
    delay_seconds: float = 2.0,
) -> bool:
    url = f"{host.rstrip('/')}/api/public/traces/{trace_id}"
    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}

    print(f"\n[Langfuse] verify GET {url}")

    for attempt in range(1, retries + 1):
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            body = resp.json()
            obs_count = len(body.get("observations") or [])
            print(
                f"[Langfuse] trace found (attempt {attempt}) "
                f"name={body.get('name')} observations={obs_count}"
            )
            if obs_count == 0:
                print("[Langfuse] WARN: trace has no generations yet — wait and retry")
                time.sleep(delay_seconds)
                continue
            return True
        if resp.status_code == 404:
            print(f"[Langfuse] not indexed yet (attempt {attempt}/{retries})")
            time.sleep(delay_seconds)
            continue
        raise RuntimeError(f"Langfuse verify failed [{resp.status_code}]: {resp.text[:300]}")

    print("[Langfuse] trace not visible yet — check UI manually")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Direct LiteLLM + Langfuse smoke test")
    parser.add_argument("--env-file", default=".env.preprod", help="Env file (default: .env.preprod)")
    parser.add_argument("--prompt", default="Reply with only the number 4.", help="Prompt sent to LiteLLM")
    parser.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout seconds")
    parser.add_argument("--skip-langfuse", action="store_true", help="Skip Langfuse logging")
    parser.add_argument("--skip-langfuse-verify", action="store_true", help="Skip Langfuse API read-back")
    args = parser.parse_args()

    env_path = ROOT / args.env_file
    cfg = load_env_file(env_path)
    if not cfg:
        print(f"ERROR: env file not found or empty: {env_path}", file=sys.stderr)
        return 1

    litellm_url = cfg.get("LITELLM_BASE_URL", "http://localhost:4000")
    litellm_key = cfg.get("LITELLM_MASTER_KEY", "")
    model = cfg.get("LLM_MODEL", "together_ai/meta-llama/Meta-Llama-3-8B-Instruct-Lite")

    langfuse_enabled = cfg.get("LANGFUSE_ENABLED", "true").lower() == "true"
    langfuse_host = cfg.get("LANGFUSE_HOST", "https://langfuse.munish.org")
    langfuse_public = cfg.get("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret = cfg.get("LANGFUSE_SECRET_KEY", "")

    if not litellm_key:
        print("ERROR: LITELLM_MASTER_KEY missing in env file", file=sys.stderr)
        return 1

    trace_id = str(uuid.uuid4())
    prompt = f"{args.prompt} [trace={trace_id}]"

    print("=== MCP direct integration test ===", flush=True)
    print(f"env: {env_path.name}", flush=True)
    print(f"trace_id: {trace_id}", flush=True)

    litellm_ok = False
    langfuse_ok = True

    try:
        answer, latency, usage = test_litellm(
            base_url=litellm_url,
            api_key=litellm_key,
            model=model,
            prompt=prompt,
            timeout=args.timeout,
        )
        litellm_ok = True
    except Exception as exc:
        print(f"\nFAIL LiteLLM: {exc}", file=sys.stderr)
        print("Tip: port-forward LiteLLM → kubectl -n am-ai port-forward svc/litellm 4000:4000", file=sys.stderr)
        return 1

    if not args.skip_langfuse and langfuse_enabled:
        if not langfuse_public or not langfuse_secret:
            print("\nWARN Langfuse keys missing — skipping trace")
        else:
            try:
                send_langfuse_trace(
                    host=langfuse_host,
                    public_key=langfuse_public,
                    secret_key=langfuse_secret,
                    trace_id=trace_id,
                    prompt=prompt,
                    response=answer,
                    model=model,
                    latency=latency,
                    usage=usage,
                )
                if not args.skip_langfuse_verify:
                    langfuse_ok = verify_langfuse_trace(
                        host=langfuse_host,
                        public_key=langfuse_public,
                        secret_key=langfuse_secret,
                        trace_id=trace_id,
                    )
            except Exception as exc:
                print(f"\nFAIL Langfuse: {exc}", file=sys.stderr)
                print(
                    "Tip: confirm LANGFUSE_HOST and project API keys in Langfuse → Settings → API Keys",
                    file=sys.stderr,
                )
                langfuse_ok = False

    print("\n=== Summary ===")
    print(f"LiteLLM : {'OK' if litellm_ok else 'FAIL'}")
    if not args.skip_langfuse and langfuse_enabled and langfuse_public:
        print(f"Langfuse: {'OK' if langfuse_ok else 'FAIL'}")
        print(f"UI      : {langfuse_host}/trace/{trace_id}")
    print(f"trace_id: {trace_id}")

    if not litellm_ok:
        return 1
    if not args.skip_langfuse and langfuse_enabled and langfuse_public and not langfuse_ok:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
