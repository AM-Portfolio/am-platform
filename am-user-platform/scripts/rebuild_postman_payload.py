import json
import pathlib

src = pathlib.Path(__file__).resolve().parents[1] / "postman" / "AM-User-Platform.postman_collection.json"
out = pathlib.Path(__file__).resolve().parents[1] / "postman" / "_upload_payload.json"
d = json.loads(src.read_text(encoding="utf-8"))
d["info"].pop("_postman_id", None)
d["info"]["schema"] = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
vars_ = d.setdefault("variable", [])
if not any(v.get("key") == "identity_base_url" for v in vars_):
    vars_.insert(1, {"key": "identity_base_url", "value": "https://am.asrax.in"})
for v in vars_:
    if v.get("key") == "keycloak_url":
        v["value"] = "https://auth.asrax.in/auth"
payload = {
    "info": d["info"],
    "item": d["item"],
    "event": d.get("event", []),
    "variable": vars_,
}
out.write_text(json.dumps(payload), encoding="utf-8")
print("ok", out.stat().st_size)
