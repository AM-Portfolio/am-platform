"""Structured service-call logger for AM Platform.

Provides high-level and low-level structured logging for external service calls
(Keycloak, HTTP, Kafka, DB, etc.) with automatic sensitive-field masking.

Usage:
    from am_platform_common.service_logger import slog

    # High-level: just know that a service call happened
    async with slog.call("keycloak", "authenticate", user="kumar@example.com"):
        result = await keycloak.post(...)

    # Low-level: log individual steps inside a flow
    slog.step("keycloak", "authenticate", "building token form", client_id="am-web-client")
    slog.step("keycloak", "authenticate", "sending POST to OIDC token endpoint", url=token_url)
"""

import asyncio
import datetime
import inspect
import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx

from am_platform_common.logging import get_correlation_context

_MASKED = "***"

_SENSITIVE_KEYS = frozenset(
    {
        "password", "passwd", "secret", "client_secret", "token", "access_token",
        "refresh_token", "id_token", "authorization", "x-api-key", "api_key",
        "keycloak_admin_password", "admin_password", "credentials",
        "otp", "code", "pin", "card_number", "cvv",
    }
)

_PII_KEYS = frozenset({"user", "username", "email", "email_id", "email_address"})


def _mask_pii(value: Any) -> Any:
    if not isinstance(value, str):
        return "***"
    if "@" in value:
        local, domain = value.split("@", 1)
        if len(local) > 2:
            local = f"{local[0]}***{local[-1]}"
        else:
            local = "***"
        return f"{local}@{domain}"
    if len(value) > 4:
        return f"{value[:2]}***{value[-2:]}"
    return "***"


def _mask(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in data.items():
        k_lower = k.lower()
        if k_lower in _SENSITIVE_KEYS:
            out[k] = _MASKED
        elif k_lower in _PII_KEYS:
            out[k] = _mask_pii(v)
        elif isinstance(v, dict):
            out[k] = _mask(v)
        else:
            out[k] = v
    return out


class ServiceLogger:
    """Structured logger conforming to am-parser AMLogger standards."""

    def __init__(self, service_name: str = "am-identity", cls_url: str = "http://am-logging-svc"):
        self.service_name = service_name
        self.cls_url = cls_url
        self.persist_to_db = os.getenv("AM_LOGGING_PERSIST_TO_DB", "False").lower() == "true"
        self._log = logging.getLogger(service_name)
        if not self._log.handlers:
            handler = logging.StreamHandler()
            self._log.addHandler(handler)

    def _format_message(self, level: str, trace_id: str, span_id: str, clazz: str, method: str, message: str, context: dict) -> str:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # Enforcing Pattern: [{timestamp}] | [{service}] | [{trace_id}:{span_id}] | [{level}] | [{class}.{method}] | {message} | {context}
        return f"[{timestamp}] | [{self.service_name}] | [{trace_id}:{span_id}] | [{level}] | [{clazz}.{method}] | {message} | {json.dumps(context)}"

    async def _send_to_cls(self, log_entry: dict):
        try:
            async with httpx.AsyncClient() as client:
                await client.post(f"{self.cls_url}/v1/logs", json=log_entry, timeout=2.0)
        except Exception as e:
            # Fallback (Zero Log Loss strategy)
            pass

    def _emit(self, level_name: str, message: str, context: dict, operation: str = "Global"):
        safe_ctx = _mask(context)
        ctx_dict = get_correlation_context()
        trace_id = ctx_dict.get("trace_id", "0000000000000000")
        span_id = ctx_dict.get("span_id", "00000000")
        
        # We try to infer the class, but since this is called from helper methods, we default to the operation name
        formatted_msg = self._format_message(level_name, trace_id, span_id, "ServiceLogger", operation, message, safe_ctx)
        
        level_val = getattr(logging, level_name, logging.INFO)
        self._log.log(level_val, formatted_msg)

        log_entry = {
            "trace_id": trace_id,
            "span_id": span_id,
            "service": self.service_name,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "log_type": "TECHNICAL",
            "level": level_name,
            "payload": {"message": message},
            "context": {
                "class": "ServiceLogger",
                "method": operation,
                "inputs": safe_ctx,
            },
            "metadata": {
                "persist_to_db": str(self.persist_to_db).lower()
            }
        }
        try:
            asyncio.create_task(self._send_to_cls(log_entry))
        except RuntimeError:
            # In case no event loop is running
            pass


    @asynccontextmanager
    async def call(
        self,
        service: str,
        operation: str,
        outcome_field: str = "result",
        **context: Any,
    ) -> AsyncGenerator[None, None]:
        start = time.perf_counter()
        self._emit("INFO", f"ENTERING {service.upper()} {operation}", context, operation=operation)

        try:
            yield
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            err_ctx = {**context, "exception": str(exc), "latency_ms": round(elapsed_ms, 2)}
            self._emit("ERROR", f"FAILED {service.upper()} {operation}", err_ctx, operation=operation)
            raise
        else:
            elapsed_ms = (time.perf_counter() - start) * 1000
            success_ctx = {**context, "outputs": {"result": "success"}, "latency_ms": round(elapsed_ms, 2)}
            self._emit("INFO", f"EXITING {service.upper()} {operation}", success_ctx, operation=operation)

    def step(
        self,
        service: str,
        operation: str,
        description: str,
        level: int = logging.DEBUG,
        **context: Any,
    ) -> None:
        level_name = logging.getLevelName(level)
        self._emit(level_name, f"STEP [{service.upper()}] {description}", context, operation=operation)

    def http(
        self,
        service: str,
        operation: str,
        method: str,
        url: str,
        status_code: int | None = None,
        elapsed_ms: float | None = None,
        **context: Any,
    ) -> None:
        level_name = "INFO" if (status_code is None or status_code < 400) else "WARNING"
        parts = [f"{method.upper()} {url}"]
        if status_code is not None:
            parts.append(f"-> {status_code}")
        if elapsed_ms is not None:
            parts.append(f"({elapsed_ms:.1f} ms)")
            
        self._emit(level_name, f"HTTP [{service.upper()}] {' '.join(parts)}", context, operation=operation)

# Module-level singleton
slog = ServiceLogger()

