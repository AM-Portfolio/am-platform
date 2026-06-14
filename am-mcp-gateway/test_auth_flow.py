import requests
import json

# 1. Verify JWKS endpoint
jwks_url = "http://auth.munish.org/auth/realms/am-preprod-realm/protocol/openid-connect/certs"
resp = requests.get(jwks_url, headers={"User-Agent": "am-platform-security/1.0", "Accept": "application/json"}, timeout=10)
print(f"JWKS status: {resp.status_code}")
if resp.status_code == 200:
    keys = resp.json().get("keys", [])
    print(f"Keys found: {len(keys)}")
    for k in keys:
        print(f"  kid={k.get('kid')}, alg={k.get('alg')}, use={k.get('use')}")
else:
    print(resp.text[:200])

# 2. Get token via client credentials
print("\n--- Client credentials token ---")
token_url = "http://auth.munish.org/auth/realms/am-preprod-realm/protocol/openid-connect/token"
resp2 = requests.post(token_url, data={
    "grant_type": "client_credentials",
    "client_id": "am-mcp-service",
    "client_secret": "hkk4698D7xZ8m2VpPL3zNfepAoTwRN8r",
}, timeout=10)
print(f"Token status: {resp2.status_code}")
if resp2.status_code == 200:
    token_data = resp2.json()
    access_token = token_data["access_token"]
    # Decode header to see kid
    header_b64 = access_token.split(".")[0]
    padding = 4 - len(header_b64) % 4
    header = json.loads(__import__("base64").urlsafe_b64decode(header_b64 + "=" * padding))
    print(f"Token kid: {header.get('kid')}")
    print(f"Token alg: {header.get('alg')}")

    # 3. Call the MCP gateway
    print("\n--- MCP Gateway call ---")
    chat_resp = requests.post("http://localhost:8120/api/v1/chat/sync",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        },
        json={
            "messages": [{"role": "user", "content": "Hello, what is 2+2?"}],
            "stream": False
        },
        timeout=30
    )
    print(f"Chat status: {chat_resp.status_code}")
    try:
        print(json.dumps(chat_resp.json(), indent=2)[:2000])
    except Exception:
        print(chat_resp.text[:500])
else:
    print(resp2.text[:300])
