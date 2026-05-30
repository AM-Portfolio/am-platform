#!/usr/bin/env python3
"""Run am-platform services together; one crash does not stop the others."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from platform_env import PLATFORM_ROOT, identity_env, notification_env, subscription_env
from uvicorn_runner import build_uvicorn_args


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    module: str
    cwd_name: str
    env_fn: Callable[[], dict[str, str]]
    port: str


SERVICES: tuple[ServiceSpec, ...] = (
    ServiceSpec("identity", "am_identity.main:app", "am-identity", identity_env, "8113"),
    ServiceSpec("subscription", "am_subscription.main:app", "am-subscription", subscription_env, "8110"),
    ServiceSpec("notification", "am_notification.main:app", "am-notification", notification_env, "8111"),
)


def parse_service_filter() -> set[str] | None:
    raw = os.environ.get("PLATFORM_DEV_SERVICES", "").strip()
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def select_services() -> list[ServiceSpec]:
    names = parse_service_filter()
    if names is None:
        return list(SERVICES)
    known = {spec.name for spec in SERVICES}
    unknown = names - known
    if unknown:
        print(f"Unknown PLATFORM_DEV_SERVICES entries: {', '.join(sorted(unknown))}")
        print(f"Valid values: {', '.join(sorted(known))}")
        sys.exit(1)
    return [spec for spec in SERVICES if spec.name in names]


def _pipe_reader(stream, prefix: str, lock: threading.Lock) -> None:
    assert stream is not None
    for line in iter(stream.readline, b""):
        text = line.decode("utf-8", errors="replace")
        with lock:
            sys.stdout.write(f"[{prefix}] {text}")
            sys.stdout.flush()
    stream.close()


class PlatformSupervisor:
    def __init__(self, specs: list[ServiceSpec], *, reload: bool) -> None:
        self.specs = specs
        self.reload = reload
        self.procs: dict[str, subprocess.Popen[bytes]] = {}
        self.reported: set[str] = set()
        self.lock = threading.Lock()
        self._stop_requested = False

    def spawn(self, spec: ServiceSpec) -> None:
        env = spec.env_fn()
        env["APP_PORT"] = spec.port
        args = build_uvicorn_args(spec.module, port=spec.port, reload=self.reload)
        cwd = PLATFORM_ROOT / spec.cwd_name
        print(f">>> Starting [{spec.name}] on :{spec.port}", flush=True)
        print(f">>> {' '.join(args)}\n", flush=True)
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.procs[spec.name] = proc
        thread = threading.Thread(
            target=_pipe_reader,
            args=(proc.stdout, spec.name, self.lock),
            daemon=True,
        )
        thread.start()

    def stop_all(self) -> None:
        self._stop_requested = True
        for name, proc in self.procs.items():
            if proc.poll() is None:
                print(f">>> Stopping [{name}] (pid {proc.pid})", flush=True)
                proc.terminate()
        for proc in self.procs.values():
            if proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def run(self) -> int:
        if not self.specs:
            print("No services selected.")
            return 1

        for spec in self.specs:
            self.spawn(spec)

        def handle_signal(signum: int, _frame: object) -> None:
            print("\n>>> Shutting down platform dev...", flush=True)
            self.stop_all()
            raise SystemExit(130 if signum == signal.SIGINT else 0)

        signal.signal(signal.SIGINT, handle_signal)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, handle_signal)

        exit_code = 0
        while True:
            alive = False
            for name, proc in self.procs.items():
                code = proc.poll()
                if code is None:
                    alive = True
                    continue
                if name in self.reported:
                    continue
                self.reported.add(name)
                if self._stop_requested:
                    continue
                print(
                    f"\n>>> [{name}] exited with code {code} (other services still running)",
                    flush=True,
                )
                if exit_code == 0 and code not in (0, None):
                    exit_code = code

            if not alive:
                break
            time.sleep(0.5)

        if not self._stop_requested:
            print("\n>>> All platform services stopped.", flush=True)
        return exit_code


def run_platform(*, reload: bool) -> int:
    specs = select_services()
    labels = ", ".join(f"{spec.name}:{spec.port}" for spec in specs)
    print(f"Platform dev - {labels}")
    if parse_service_filter() is None:
        print("Tip: set PLATFORM_DEV_SERVICES=identity,subscription to run a subset.\n")
    return PlatformSupervisor(specs, reload=reload).run()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "dev"
    reload = mode != "dev:prod"
    sys.exit(run_platform(reload=reload))


if __name__ == "__main__":
    main()
