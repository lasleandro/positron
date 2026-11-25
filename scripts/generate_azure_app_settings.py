"""Generate the Azure Web App application settings JSON from the repo .env.

Adapted from kirya_core/scripts/generate_azure_app_settings.py. Merges three layers, lowest
precedence first:

1. the repo ``.env`` (what runs locally; ``AZURE_PG_*`` become the app's ``POSTGRES_*``),
2. the container invariants of the single-container Web App (port, production posture, origin),
3. an optional ``.env.azure`` with deployment-specific values (e.g. a new DJANGO_SECRET_KEY).

Only keys the platform actually reads are kept (detected from exams/settings.py, plus the
container entrypoint and App Service keys). The result is validated by importing the real
Django settings in a clean environment, and written in the format accepted by both the Portal's
"Advanced edit" and ``az webapp config appsettings set --settings @file``. Secret values are
never printed.

VAULT_NAMESPACE and TOTP_ENCRYPTION_KEY must stay identical to the database's origin: every
password-derived key and every stored MFA secret depends on them.

Usage:
    python scripts/generate_azure_app_settings.py --app-name podeabrir
    python scripts/generate_azure_app_settings.py --app-name podeabrir --origin https://podeabrir.com
    python scripts/generate_azure_app_settings.py --app-name podeabrir --key-vault podeabrir-kv

Docs: docs/azure.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILE = REPO_ROOT / "exams" / "settings.py"
CONTAINER_PORT = "8000"

# Read by the App Service platform or by the container entrypoint, not by Django settings.
PLATFORM_KEYS = frozenset({
    "WEBSITES_PORT", "WEBSITES_CONTAINER_START_TIME_LIMIT", "WEBSITES_ENABLE_APP_SERVICE_STORAGE",
    "ROLE", "PORT", "GUNICORN_WORKERS", "GUNICORN_THREADS", "DB_WAIT_HOST", "DB_WAIT_PORT",
})
# Development-only knobs: never shipped (the container talks to POSTGRES_*, not the local container).
DEV_ONLY_KEYS = frozenset({
    "PG_LOCAL_HOST", "PG_LOCAL_PORT", "PG_LOCAL_USER", "PG_LOCAL_PASSWORD", "PG_LOCAL_DATABASE", "PG_LOCAL_SSLMODE",
    "BACKEND_HOST", "BACKEND_PORT", "FRONTEND_PORT", "POSTGRES_SSLMODE",
})
# Only meaningful before the first account exists; ship it only when set in .env.azure.
OVERRIDE_ONLY_KEYS = frozenset({"BOOTSTRAP_INVITE_DIGEST"})
AZURE_PG_MAP = {
    "AZURE_PG_HOST": "POSTGRES_HOST", "AZURE_PG_PORT": "POSTGRES_PORT", "AZURE_PG_DATABASE": "POSTGRES_DB",
    "AZURE_PG_USER": "POSTGRES_USER", "AZURE_PG_PASSWORD": "POSTGRES_PASSWORD",
}
EXPLICIT_SECRET_KEYS = frozenset({
    "DJANGO_SECRET_KEY", "TOTP_ENCRYPTION_KEY", "VAPID_PRIVATE_KEY", "POSTGRES_PASSWORD", "EMAIL_SMTP_PASSWORD",
})
MUST_MATCH_DATA_KEYS = ("VAULT_NAMESPACE", "TOTP_ENCRYPTION_KEY")
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"})


@dataclass
class AppSettingsResult:
    """Merged settings plus everything the operator must know before uploading."""

    values: dict[str, str]
    key_vault_secret_names: list[str] = field(default_factory=list)
    dropped_keys: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def settings_keys() -> frozenset[str]:
    """Every environment name exams/settings.py reads."""
    source = SETTINGS_FILE.read_text()
    pattern = r'(?:os\.getenv|os\.environ\.get|env_int)\(\s*"([A-Z0-9_]+)"|os\.environ\[\s*"([A-Z0-9_]+)"\s*\]'
    return frozenset(name for pair in re.findall(pattern, source) for name in pair if name)


def known_setting_keys() -> frozenset[str]:
    return (settings_keys() | PLATFORM_KEYS) - DEV_ONLY_KEYS


def container_invariants(app_name: str, origin: str | None) -> dict[str, str]:
    """Values dictated by the single-container Web App topology."""
    return {
        "APP_ENV": "production",
        "APP_ORIGIN": origin or f"https://{app_name}.azurewebsites.net",
        "WEBSITES_PORT": CONTAINER_PORT,
        "PORT": CONTAINER_PORT,
        # No files are written: documents live (encrypted) in PostgreSQL.
        "WEBSITES_ENABLE_APP_SERVICE_STORAGE": "false",
        # First boot applies every migration against the remote database.
        "WEBSITES_CONTAINER_START_TIME_LIMIT": "600",
        "ROLE": "platform",
        # Invitations, password reset and read requests need outbound email in production.
        "EMAIL_ENABLED": "true",
    }


def is_secret(key: str) -> bool:
    return key in EXPLICIT_SECRET_KEYS or key.endswith(("_PASSWORD", "_SECRET", "_PRIVATE_KEY"))


def key_vault_secret_name(key: str) -> str:
    """Key Vault names allow only alphanumerics and dashes."""
    return key.lower().replace("_", "-")


def key_vault_reference(vault_name: str, key: str) -> str:
    return f"@Microsoft.KeyVault(VaultName={vault_name};SecretName={key_vault_secret_name(key)})"


def map_azure_database(values: dict[str, str]) -> dict[str, str]:
    """Local .env keeps the Azure server under AZURE_PG_*; the app reads POSTGRES_*."""
    mapped = {target: values[source] for source, target in AZURE_PG_MAP.items() if values.get(source)}
    return {**mapped, **{key: value for key, value in values.items() if key.startswith("POSTGRES_")}}


def _settings_validation_errors(values: dict[str, str]) -> list[str]:
    """Import the real Django settings in a clean environment; report the message, never values."""
    env = {"PATH": os.environ.get("PATH", ""), "DJANGO_SETTINGS_MODULE": "exams.settings", **values}
    # settings.py loads the repo .env on import; disable it so only `values` are seen.
    probe = (
        "import dotenv\ndotenv.load_dotenv = lambda *args, **kwargs: False\nimport django\n"
        "try:\n    django.setup()\nexcept Exception as exc:\n    print(type(exc).__name__ + ': ' + str(exc)); raise SystemExit(1)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    if completed.returncode == 0:
        return []
    message = (completed.stdout or completed.stderr).strip().splitlines()
    return [f"Django settings: {message[-1] if message else 'failed to load'}"]


def _deployment_errors(values: dict[str, str], key_vault: str | None) -> list[str]:
    errors: list[str] = []
    origin = urlsplit(values.get("APP_ORIGIN", ""))
    if origin.scheme != "https" or not origin.hostname or origin.path not in ("", "/"):
        errors.append("APP_ORIGIN must be an https origin without a path")
    for key in ("POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        if not values.get(key):
            errors.append(f"{key} is required (set AZURE_PG_* in .env or POSTGRES_* in .env.azure)")
    if values.get("POSTGRES_HOST", "") in LOCAL_HOSTS:
        errors.append("POSTGRES_HOST points at a local database")
    if key_vault is None:
        for key in ("EMAIL_SMTP_HOST", "EMAIL_SMTP_USERNAME", "EMAIL_SMTP_PASSWORD", "EMAIL_FROM_ADDRESS"):
            if not values.get(key):
                errors.append(f"{key} is required because EMAIL_ENABLED=true")
    if key_vault is None:
        try:
            Fernet(values.get("TOTP_ENCRYPTION_KEY", ""))
        except ValueError:
            errors.append("TOTP_ENCRYPTION_KEY must be a valid Fernet key (the same one the data was created with)")
    if bool(values.get("VAPID_PUBLIC_KEY")) != bool(values.get("VAPID_PRIVATE_KEY")):
        errors.append("VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY must be set together")
    return errors


def _deployment_warnings(base: dict[str, str], overrides: dict[str, str], values: dict[str, str]) -> list[str]:
    warnings: list[str] = []
    if base.get("DJANGO_SECRET_KEY") and "DJANGO_SECRET_KEY" not in overrides:
        warnings.append("DJANGO_SECRET_KEY is reused from the local .env; set a production value in .env.azure")
    for key in MUST_MATCH_DATA_KEYS:
        if key in overrides and base.get(key) and overrides[key] != base[key]:
            warnings.append(f"{key} differs from the local .env: data copied from local becomes unreadable")
    if "BOOTSTRAP_INVITE_DIGEST" in values:
        warnings.append("BOOTSTRAP_INVITE_DIGEST is set: remove it once the first account exists")
    return warnings


def build_app_settings(
    base: dict[str, str],
    overrides: dict[str, str],
    app_name: str,
    origin: str | None = None,
    key_vault: str | None = None,
    validate_django: bool = True,
) -> AppSettingsResult:
    """Merge, filter and validate the settings for one Web App."""
    known = known_setting_keys()
    local = {**base, **map_azure_database(base)}
    merged = {**local, **container_invariants(app_name, origin), **overrides}
    values = {
        key: value for key, value in merged.items()
        if key in known and (key not in OVERRIDE_ONLY_KEYS or key in overrides) and value != ""
    }
    result = AppSettingsResult(values=values, dropped_keys=sorted(set(merged) - set(values)))
    result.errors = _deployment_errors(values, key_vault)
    if validate_django and not result.errors:
        result.errors += _settings_validation_errors(values)
    result.warnings = _deployment_warnings(base, overrides, values)
    if key_vault is None:
        return result
    secret_keys = sorted(key for key, value in values.items() if value and is_secret(key))
    result.values = {**values, **{key: key_vault_reference(key_vault, key) for key in secret_keys}}
    result.key_vault_secret_names = [key_vault_secret_name(key) for key in secret_keys]
    return result


def to_azure_json(values: dict[str, str]) -> str:
    """The list format used by Portal "Advanced edit" and the az CLI."""
    entries = [{"name": key, "value": values[key], "slotSetting": False} for key in sorted(values)]
    return json.dumps(entries, indent=2, ensure_ascii=False)


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {key: value for key, value in dotenv_values(path).items() if value is not None}


def _print_report(result: AppSettingsResult, output: Path | None) -> None:
    for key in sorted(result.values):
        value = result.values[key]
        shown = "<secret>" if is_secret(key) and not value.startswith("@Microsoft.KeyVault") else value
        print(f"  {key}={shown}")
    if result.dropped_keys:
        print(f"\nDropped (not read by the platform or development-only): {', '.join(result.dropped_keys)}")
    if result.key_vault_secret_names:
        print("\nCreate these Key Vault secrets before starting the app:")
        print("\n".join(f"  {name}" for name in result.key_vault_secret_names))
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")
    if output is not None:
        print(f"\nWrote {len(result.values)} settings to {output}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--app-name", required=True, help="Web App name (<app-name>.azurewebsites.net)")
    parser.add_argument("--origin", help="public origin if not the azurewebsites.net host, e.g. https://podeabrir.com")
    parser.add_argument("--env", type=Path, default=REPO_ROOT / ".env", help="base env file")
    parser.add_argument("--overrides", type=Path, default=REPO_ROOT / ".env.azure", help="deployment override env file")
    parser.add_argument("--key-vault", help="emit Key Vault references for secrets, using this vault name")
    parser.add_argument("--output", type=Path, help="output JSON path (default: var/azure/app-settings.<app-name>.json)")
    args = parser.parse_args(argv)

    result = build_app_settings(
        read_env_file(args.env), read_env_file(args.overrides), args.app_name, args.origin, args.key_vault,
    )
    if result.errors:
        _print_report(result, None)
        return 1
    output = args.output or REPO_ROOT / "var" / "azure" / f"app-settings.{args.app_name}.json"
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.write_text(to_azure_json(result.values) + "\n")
    output.chmod(0o600)
    _print_report(result, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
