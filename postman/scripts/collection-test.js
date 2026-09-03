/**
 * AM Platform — collection test script (post-response).
 * Auto-captures tokens and entity IDs into the active environment.
 */

function setEnv(key, value) {
  if (value === undefined || value === null || value === "") {
    return;
  }
  const text = typeof value === "string" ? value : String(value);
  pm.environment.set(key, text);
  pm.collectionVariables.set(key, text);
}

function jwtPayload(token) {
  try {
    const part = token.split(".")[1];
    return JSON.parse(atob(part));
  } catch (e) {
    return null;
  }
}

function isClientCredentialsRequest() {
  const url = pm.request.url.toString();
  if (!url.includes("/openid-connect/token")) {
    return false;
  }
  const body = pm.request.body;
  if (!body || body.mode !== "urlencoded") {
    return false;
  }
  return body.urlencoded.some(
    (row) => row.key === "grant_type" && row.value === "client_credentials"
  );
}

const status = pm.response.code;
pm.environment.set("last_response_status", String(status));

if (status < 200 || status >= 300) {
  return;
}

let body;
try {
  body = pm.response.json();
} catch (e) {
  return;
}

// --- OAuth / Keycloak token responses ---
if (body.access_token) {
  if (isClientCredentialsRequest()) {
    setEnv("service_access_token", body.access_token);
  } else {
    setEnv("access_token", body.access_token);
    const payload = jwtPayload(body.access_token);
    if (payload?.sub) {
      setEnv("user_sub", payload.sub);
    }
  }
}

if (body.tokens && typeof body.tokens === "object") {
  if (body.tokens.access_token) {
    setEnv("access_token", body.tokens.access_token);
    const payload = jwtPayload(body.tokens.access_token);
    if (payload?.sub) {
      setEnv("user_sub", payload.sub);
    }
  }
  if (body.tokens.refresh_token) {
    setEnv("refresh_token", body.tokens.refresh_token);
  }
}

if (body.refresh_token) {
  setEnv("refresh_token", body.refresh_token);
}

// --- Device link / web OTP / step-up ---
setEnv("device_link_id", body.device_link_id);
setEnv("confirmation_code", body.confirmation_code);
setEnv("otp_session_id", body.otp_session_id);
setEnv("step_up_token", body.step_up_token);

const amSessionCookie = pm.cookies.get("am_session");
if (amSessionCookie) {
  setEnv("am_session", amSessionCookie);
}

if (Array.isArray(body) && body.length) {
  if (body[0].session_id) {
    setEnv("login_session_id", body[0].session_id);
  }
  if (body[0].event_id) {
    setEnv("security_event_id", body[0].event_id);
  }
}

// --- Identity auth helpers ---
setEnv("google_state", body.state);
setEnv("google_auth_url", body.auth_url);

if (body.sub) {
  setEnv("user_sub", body.sub);
}

// --- Standard API envelope { data: ... } ---
const data = body.data !== undefined ? body.data : null;

if (data && typeof data === "object" && !Array.isArray(data)) {
  if (data.id) {
    setEnv("subscription_id", data.id);
    if (urlLooksLikeNotification()) {
      setEnv("notification_id", data.id);
    }
  }
  if (data.user_id) {
    setEnv("user_sub", data.user_id);
  }
  if (data.sub) {
    setEnv("user_sub", data.sub);
  }
  if (data.plan_code) {
    setEnv("plan_code", data.plan_code);
  }
  if (data.notification_id) {
    setEnv("notification_id", data.notification_id);
  }
}

if (Array.isArray(data) && data.length && data[0]?.code) {
  setEnv("plan_code", data[0].code);
}

// --- Flat profile / user responses ---
if (body.settings !== undefined && body.sub) {
  setEnv("user_sub", body.sub);
}

function urlLooksLikeNotification() {
  return pm.request.url.toString().includes("/notifications");
}

// Console summary for quick debugging in Postman runner.
const captured = [
  pm.environment.get("access_token") ? "access_token" : null,
  pm.environment.get("service_access_token") ? "service_access_token" : null,
  pm.environment.get("user_sub") ? "user_sub" : null,
  pm.environment.get("subscription_id") ? "subscription_id" : null,
  pm.environment.get("notification_id") ? "notification_id" : null,
  pm.environment.get("device_link_id") ? "device_link_id" : null,
  pm.environment.get("am_session") ? "am_session" : null,
  pm.environment.get("step_up_token") ? "step_up_token" : null,
  pm.environment.get("login_session_id") ? "login_session_id" : null,
  pm.environment.get("security_event_id") ? "security_event_id" : null,
].filter(Boolean);

if (captured.length) {
  console.log("[AM Platform] env updated:", captured.join(", "));
}
