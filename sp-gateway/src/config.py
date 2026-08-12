"""Configuration for the SimplePractice gateway.

Loads credentials from the environment. Nothing in here is ever logged: the
Settings object deliberately has no __repr__ that could print a secret, and
secret values are wrapped so an accidental print/format yields a mask.

Env var names match D:\\Clinican Modeliaitlities\\.env.local exactly
(SP_Email / SP_Password) but are read case-insensitively so a future rename to
SP_EMAIL / SP_PASSWORD keeps working.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_ROOT = Path(__file__).resolve().parents[1]

# SimplePractice hosts we are ever allowed to touch. Anything else is refused
# by safety.assert_allowed_url() before a socket is opened.
SP_APP_HOST = "secure.simplepractice.com"
# Sign-in is NOT on the app host. secure.simplepractice.com issues a SAML request
# and redirects to account.simplepractice.com/saml/auth, where the actual login
# form lives; a SAML response then bounces back. Both hosts must be allowed or
# the request guard aborts the redirect chain mid-flight.
SP_ACCOUNT_HOST = "account.simplepractice.com"
SP_PORTAL_HOST = "mcnultycw.clientsecure.me"

SP_LOGIN_HOST = SP_APP_HOST  # kept as the entry point for the sign-in flow
ALLOWED_HOSTS = frozenset({SP_APP_HOST, SP_ACCOUNT_HOST, SP_PORTAL_HOST})

PRACTICE_ID = "226118"


class Secret:
    """A string that refuses to print itself.

    Guards against the single most common way credentials escape: an f-string
    in a log line, or a traceback that renders local variables.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """The only way to read the value. Call at the point of use, never earlier."""
        return self._value

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "<Secret ****>"

    __str__ = __repr__

    def __format__(self, _spec: str) -> str:  # pragma: no cover - trivial
        return "<Secret ****>"

    def __bool__(self) -> bool:
        return bool(self._value)


def _env(*names: str, default: str | None = None) -> str | None:
    """Read the first env var that is set, trying exact then case-variant names."""
    for name in names:
        if name in os.environ and os.environ[name].strip():
            return os.environ[name].strip()
    lowered = {k.lower(): v for k, v in os.environ.items()}
    for name in names:
        v = lowered.get(name.lower())
        if v and v.strip():
            return v.strip()
    return default


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader. No dependency, no surprises, does not overwrite real env."""
    path = path or (REPO_ROOT / ".env.local")
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    sp_email: Secret
    sp_password: Secret
    session_key: Secret | None = None
    # Supabase is the only place output goes. The service key bypasses row-level
    # security, so it belongs in Fly secrets and must never reach a browser.
    supabase_url: str | None = None
    supabase_service_key: Secret | None = None
    headless: bool = True
    # Hard ceiling on SimplePractice requests PER RUN of a feed. A stop, not a
    # warning. Named per_run rather than daily because that is what it actually
    # is — a fresh RequestBudget is constructed for every feed execution, so a
    # "daily" name would have implied a cross-cycle guarantee that does not exist.
    per_run_request_budget: int = 500
    # Politeness window between requests, per the practice's own stated rule.
    min_delay_s: float = 0.7
    max_delay_s: float = 1.8
    state_dir: Path = field(default=GATEWAY_ROOT / "state")

    @property
    def configured(self) -> bool:
        return bool(self.sp_email) and bool(self.sp_password)


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        sp_email=Secret(_env("SP_Email", "SP_EMAIL", default="") or ""),
        sp_password=Secret(_env("SP_Password", "SP_PASSWORD", default="") or ""),
        session_key=Secret(_env("SP_SESSION_KEY", default="") or "") or None,
        supabase_url=_env("SUPABASE_URL"),
        supabase_service_key=Secret(_env("SUPABASE_SERVICE_KEY", default="") or "") or None,
        headless=(_env("SP_HEADLESS", default="1") or "1") not in ("0", "false", "False"),
        state_dir=Path(_env("SP_STATE_DIR", default=str(GATEWAY_ROOT / "state"))),
    )
