#!/usr/bin/env python3
"""Run am-user-platform tests with monorepo PYTHONPATH."""

from __future__ import annotations

import subprocess
import sys

from platform_env import PLATFORM_ROOT, python_exe, user_platform_env


def main() -> int:
    env = user_platform_env()
    args = [python_exe(), "-m", "pytest", "tests", "-q", *sys.argv[1:]]
    return subprocess.run(args, cwd=PLATFORM_ROOT / "am-user-platform", env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
