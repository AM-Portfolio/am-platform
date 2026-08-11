"""Local-only credential files on disk. Never uploaded off-machine by this service."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from am_mcp_hub.core.config import get_settings

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples" / "credentials"


@dataclass(frozen=True, slots=True)
class CredFileInfo:
    name: str
    path: str
    exists: bool
    size_bytes: int
    keys_set: int
    keys_total: int
    sample_available: bool


def creds_root() -> Path:
    settings = get_settings()
    root = Path(settings.local_creds_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    (root / "credentials.d").mkdir(parents=True, exist_ok=True)
    (root / "secrets").mkdir(parents=True, exist_ok=True)
    return root


def samples_root() -> Path:
    return SAMPLES_DIR


def ensure_samples_copied(*, overwrite: bool = False) -> list[str]:
    root = creds_root()
    copied: list[str] = []
    src = samples_root()
    if not src.is_dir():
        return copied
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        dest = root / "samples" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not overwrite:
            continue
        shutil.copy2(path, dest)
        copied.append(str(rel).replace("\\", "/"))
    readme = root / "README.txt"
    if not readme.exists():
        readme.write_text(
            "LOCAL CREDENTIALS — stay on this machine only.\n"
            "Hub never uploads these files to the internet.\n"
            "Deleting the Docker app does NOT delete this folder when bind-mounted.\n"
            "Fill samples/ then copy into credentials.env or credentials.d/<name>.env\n"
            "Or use the Admin UI Credentials / Onboard tabs.\n",
            encoding="utf-8",
        )
    return copied


def _parse_keys(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        t = line.strip()
        if not t or t.startswith("#") or "=" not in t:
            continue
        m = _KEY_RE.match(t)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        out[k] = v
    return out


def list_cred_files() -> list[CredFileInfo]:
    root = creds_root()
    infos: list[CredFileInfo] = []
    candidates = [root / "credentials.env"]
    d = root / "credentials.d"
    if d.is_dir():
        candidates.extend(sorted(d.glob("*.env")))
    for path in candidates:
        rel = str(path.relative_to(root)).replace("\\", "/")
        exists = path.is_file()
        text = path.read_text(encoding="utf-8") if exists else ""
        keys = _parse_keys(text) if text else {}
        set_n = sum(1 for v in keys.values() if v.strip())
        name = "credentials.env" if path.name == "credentials.env" and path.parent == root else f"credentials.d/{path.name}"
        infos.append(
            CredFileInfo(
                name=name,
                path=rel,
                exists=exists,
                size_bytes=path.stat().st_size if exists else 0,
                keys_set=set_n,
                keys_total=len(keys),
                sample_available=True,
            )
        )
    return infos


def read_file(rel: str) -> str:
    path = _resolve(rel)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def write_file(rel: str, content: str) -> CredFileInfo:
    path = _resolve(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8")
    load_into_environ()
    rel_norm = str(path.relative_to(creds_root())).replace("\\", "/")
    keys = _parse_keys(content)
    name = "credentials.env" if rel_norm == "credentials.env" else rel_norm
    return CredFileInfo(
        name=name,
        path=rel_norm,
        exists=True,
        size_bytes=path.stat().st_size,
        keys_set=sum(1 for v in keys.values() if v.strip()),
        keys_total=len(keys),
        sample_available=True,
    )


def save_secret_upload(filename: str, data: bytes) -> dict[str, str]:
    safe = Path(filename).name
    if not safe or ".." in safe:
        raise ValueError("invalid filename")
    dest = creds_root() / "secrets" / safe
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    load_into_environ()
    return {"path": f"secrets/{safe}", "bytes": str(len(data))}


def list_samples() -> list[dict[str, str]]:
    src = samples_root()
    out: list[dict[str, str]] = []
    if not src.is_dir():
        return out
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".env", ".example", ".json"} and not path.name.endswith(
            ".json.example"
        ):
            if path.suffix != ".env" and ".example" not in path.name:
                continue
        rel = str(path.relative_to(src)).replace("\\", "/")
        out.append(
            {
                "id": rel,
                "name": path.name,
                "title": path.stem.replace("_", " ").replace("-", " ").title(),
                "target": _default_target(rel),
            }
        )
    return out


def read_sample(sample_id: str) -> str:
    return _resolve_sample(sample_id).read_text(encoding="utf-8")


def apply_sample(sample_id: str, *, overwrite: bool = False) -> dict[str, str]:
    sample_path = _resolve_sample(sample_id)
    target = _default_target(sample_id)
    if sample_id.startswith("secrets/") or sample_path.suffix == ".json" or sample_id.endswith(
        ".json.example"
    ):
        dest_name = sample_path.name.replace(".example", "")
        dest = creds_root() / "secrets" / dest_name
        if dest.exists() and not overwrite:
            return {"status": "exists", "target": f"secrets/{dest_name}"}
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sample_path, dest)
        load_into_environ()
        return {"status": "written", "target": f"secrets/{dest_name}"}
    path = _resolve(target)
    if path.exists() and not overwrite:
        return {"status": "exists", "target": target, "message": "File exists; pass overwrite=true"}
    write_file(target, sample_path.read_text(encoding="utf-8"))
    return {"status": "written", "target": target}


def _collect_cred_files(home: Path, files: list[Path]) -> None:
    if not home.is_dir():
        return
    vault = home / "credentials.vault.env"
    if vault.is_file():
        files.append(vault)
    d = home / "credentials.d"
    if d.is_dir():
        files.extend(sorted(d.glob("*.env")))
    main = home / "credentials.env"
    if main.is_file():
        files.append(main)


def load_into_environ(*, override: bool = False) -> int:
    settings = get_settings()
    merged: dict[str, str] = {}
    files: list[Path] = []

    # Weak -> strong: real home dirs (native Hub), compose mounts, then hub local-creds.
    for home_raw in (
        str(Path.home() / ".am"),
        str(Path.home() / ".asrax"),
        settings.laptop_am_dir,
        settings.laptop_asrax_dir,
    ):
        _collect_cred_files(Path(home_raw).expanduser(), files)

    root = creds_root()
    vault = root / "credentials.vault.env"
    if vault.is_file():
        files.append(vault)
    d = root / "credentials.d"
    if d.is_dir():
        files.extend(sorted(d.glob("*.env")))
    main = root / "credentials.env"
    if main.is_file():
        files.append(main)

    for path in files:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        merged.update({k: v for k, v in _parse_keys(text).items() if v})

    loaded = 0
    for k, v in merged.items():
        if override or not os.environ.get(k):
            os.environ[k] = v
            loaded += 1

    for home_raw in (settings.laptop_asrax_dir, settings.laptop_am_dir, str(root)):
        secrets = Path(home_raw).expanduser() / "secrets"
        oauth = secrets / "google-oauth-client.json"
        if oauth.is_file():
            for env_key in (
                "GOOGLE_OAUTH_CLIENT_FILE",
                "GOOGLE_DRIVE_OAUTH_CREDENTIALS",
            ):
                if override or not os.environ.get(env_key):
                    os.environ[env_key] = str(oauth)
                    loaded += 1
            break
    return loaded


def resolve_env_secret(*keys: str) -> str:
    """Refresh local credential merge, then return the first non-empty env value."""
    load_into_environ()
    for key in keys:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def status_summary() -> dict[str, object]:
    root = creds_root()
    ensure_samples_copied()
    n = load_into_environ()
    return {
        "local_only": True,
        "never_uploaded": True,
        "persist_note": "Bind-mounted host folder; survives docker image/container delete",
        "root": str(root),
        "files": [asdict(f) for f in list_cred_files()],
        "samples": list_samples(),
        "environ_keys_loaded": n,
    }


def onboard_catalog() -> list[dict[str, object]]:
    """UI checklist for enabling MCP tools locally."""
    return [
        {
            "slug": "github",
            "title": "GitHub",
            "sample": "github.env",
            "steps": ["Apply sample github.env", "Paste PAT", "Enable integration", "Open Inspector"],
        },
        {
            "slug": "vault",
            "title": "Vault",
            "sample": "vault.env",
            "steps": ["Apply sample vault.env", "Set VAULT_TOKEN", "Enable vault", "Open Inspector"],
        },
        {
            "slug": "litellm",
            "title": "LiteLLM",
            "sample": "litellm.env",
            "steps": ["Apply sample litellm.env", "Optional master key", "Enable litellm"],
        },
        {
            "slug": "google-workspace",
            "title": "Google Workspace",
            "sample": "google.env",
            "steps": [
                "Apply google.env + secrets/google-oauth-client.json.example",
                "Fill OAuth client",
                "Enable google-workspace",
                "Inspector → google-workspace → Connect",
            ],
        },
        {
            "slug": "asrax",
            "title": "Asrax hub key",
            "sample": "asrax.env",
            "steps": ["Apply asrax.env", "Set ASRAX_KEY_ID/SECRET", "Use @asrax/mcp in Cursor"],
        },
        {
            "slug": "observability",
            "title": "Grafana / Argo / Cloudflare",
            "sample": "observability.env",
            "steps": ["Apply observability.env", "Fill tokens you need"],
        },
        {
            "slug": "infra",
            "title": "Keycloak / Kafka / MinIO / Zoho",
            "sample": "infra.env",
            "steps": ["Apply infra.env", "Fill only services you use"],
        },
    ]


def default_target(sample_id: str) -> str:
    return _default_target(sample_id)


def parse_env_keys(text: str) -> dict[str, str]:
    return _parse_keys(text)


def _default_target(sample_id: str) -> str:
    name = Path(sample_id).name
    if name in {"core.env", "credentials.env"}:
        return "credentials.env"
    if "secrets/" in sample_id.replace("\\", "/"):
        return f"secrets/{name.replace('.example', '')}"
    stem = Path(name).stem
    return f"credentials.d/{stem}.env"


def _resolve(rel: str) -> Path:
    rel = rel.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        raise ValueError("invalid path")
    root = creds_root().resolve()
    path = (root / rel).resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("path escapes creds root")
    parts = path.relative_to(root).parts
    if parts[0] == "credentials.env" and len(parts) == 1:
        return path
    if parts[0] == "credentials.d" and len(parts) == 2 and parts[1].endswith(".env"):
        return path
    if parts[0] == "secrets" and len(parts) >= 2:
        return path
    if parts[0] == "samples":
        return path
    if len(parts) == 1 and parts[0].endswith(".env"):
        return path
    raise ValueError("only credentials.env, credentials.d/*.env, or secrets/* allowed")


def _resolve_sample(sample_id: str) -> Path:
    sample_id = sample_id.replace("\\", "/").lstrip("/")
    if ".." in sample_id.split("/"):
        raise ValueError("invalid sample id")
    root = samples_root().resolve()
    path = (root / sample_id).resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("sample escapes")
    if not path.is_file():
        raise FileNotFoundError(sample_id)
    return path
