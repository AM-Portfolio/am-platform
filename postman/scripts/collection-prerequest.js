/**
 * AM Platform — collection pre-request script.
 * Runs before every request. Uses environment variables only (no hardcoded URLs).
 */

function setIfMissing(key, value) {
  if (!pm.environment.get(key) && value) {
    pm.environment.set(key, value);
  }
}

// Ensure idempotency key exists for meter/check POSTs (regenerated per request below).
const method = pm.request.method;
const url = pm.request.url.toString();
const isMeterOrCheck =
  method === "POST" &&
  (url.includes("/internal/check") ||
    url.includes("/internal/meter") ||
    url.includes("/subscriptions/internal/"));

if (isMeterOrCheck || !pm.environment.get("idempotency_key")) {
  pm.environment.set("idempotency_key", pm.variables.replaceIn("{{$guid}}"));
}

// Optional correlation header for platform services (ignored if unsupported).
if (!pm.request.headers.has("X-Request-Id")) {
  pm.request.headers.add({
    key: "X-Request-Id",
    value: pm.variables.replaceIn("{{$guid}}"),
  });
}

pm.environment.set("last_request_name", pm.info.requestName || "");
pm.environment.set("last_request_url", url);
