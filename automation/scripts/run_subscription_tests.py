#!/usr/bin/env python3
"""Run am-subscription tests with monorepo PYTHONPATH."""

from __future__ import annotations

import subprocess
import sys

from platform_env import PLATFORM_ROOT, python_exe, subscription_env


def main() -> int:
    env = subscription_env()
    args = [python_exe(), "-m", "pytest", "tests", "-q", *sys.argv[1:]]
    return subprocess.run(
        args, cwd=PLATFORM_ROOT / "am-subscription", env=env
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
