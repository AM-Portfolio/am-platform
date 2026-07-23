"""Shared uvicorn launch helpers for am-platform dev scripts."""

from __future__ import annotations

from platform_env import python_exe


def build_uvicorn_args(module: str, *, port: str, reload: bool) -> list[str]:
    args = [
        python_exe(),
        "-m",
        "uvicorn",
        module,
        "--host",
        "0.0.0.0",
        "--port",
        port,
    ]
    if reload:
        args.append("--reload")
    return args
