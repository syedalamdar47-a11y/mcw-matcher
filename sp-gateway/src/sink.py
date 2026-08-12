"""Where aggregate output goes.

The gateway never lets a consumer talk to it. It PUSHES finished, reduced rows
into Supabase, and consumers (the Matcher, Mothership, anything future) only ever
READ Supabase. That direction matters: it means a consumer can never trigger a
SimplePractice request, so no amount of consumer traffic can hammer the practice's
vendor or widen what data is reachable.

The service key used here bypasses row-level security, so it lives ONLY in Fly
secrets and never in anything a browser loads.

If Supabase is not configured the sink degrades to logging a count. That is
deliberate: it makes the whole pipeline runnable end-to-end for a smoke test
without provisioning anything.
"""

from __future__ import annotations

from typing import Any, Sequence

from .config import Settings
from .safety import log


class Sink:
    def __init__(self, settings: Settings) -> None:
        self._url = settings.supabase_url
        self._key = settings.supabase_service_key
        self._local_dir = settings.state_dir / "output"

    @property
    def configured(self) -> bool:
        return bool(self._url and self._key)

    def upsert(self, table: str, rows: Sequence[dict[str, Any]],
               *, on_conflict: str | None = None) -> int:
        """Idempotent write. Re-running a feed repairs rather than duplicates.

        This is what makes a missed night self-healing: the next run recomputes
        the same natural keys and overwrites, so nobody has to reconcile by hand.
        """
        if not rows:
            return 0
        # Keys beginning with "_" are the feed's own scratch values (ids it needed
        # mid-run, not columns). Stripping them here rather than at each call site
        # means a feed can carry working state on its rows without every future
        # author remembering to clean up before the write.
        rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
        if not self.configured:
            return self._write_local(table, rows)

        import httpx

        endpoint = f"{self._url.rstrip('/')}/rest/v1/{table}"
        params = {"on_conflict": on_conflict} if on_conflict else None
        headers = {
            "apikey": self._key.reveal(),
            "Authorization": f"Bearer {self._key.reveal()}",
            "Content-Type": "application/json",
            # merge-duplicates = upsert; return=minimal so the response body
            # never echoes back data we would then have to scrub.
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(endpoint, json=list(rows), params=params, headers=headers)
        if resp.status_code >= 300:
            # Body may quote the offending row, so it is never logged.
            raise RuntimeError(
                f"Supabase write to {table} failed with HTTP {resp.status_code}"
            )
        log(step="sink", status="ok", rows=len(rows))
        return len(rows)

    def fetch_existing_slots(self) -> dict[str, dict[str, Any]]:
        """What we already know, so we only re-fetch what actually needs it.

        Returns {} on any problem: not knowing simply means the caller refreshes
        more clinicians this cycle, which is wasteful but never wrong.
        """
        if not self.configured:
            return {}
        import httpx

        try:
            with httpx.Client(timeout=20) as client:
                resp = client.get(
                    f"{self._url.rstrip('/')}/rest/v1/clinician_availability",
                    params={"select": "sp_clinician_id,next_available_at,slots,slots_fetched_at,days"},
                    headers={"apikey": self._key.reveal(),
                             "Authorization": f"Bearer {self._key.reveal()}"},
                )
            if resp.status_code >= 300:
                return {}
            return {str(r["sp_clinician_id"]): r for r in resp.json()
                    if r.get("sp_clinician_id")}
        except Exception:
            return {}

    def _current_failures(self, feed: str) -> int:
        """Read the current consecutive_failures for a feed. 0 if unknown."""
        if not self.configured:
            return 0
        import httpx

        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    f"{self._url.rstrip('/')}/rest/v1/gateway_health",
                    params={"feed": f"eq.{feed}", "select": "consecutive_failures"},
                    headers={"apikey": self._key.reveal(),
                             "Authorization": f"Bearer {self._key.reveal()}"},
                )
            if resp.status_code >= 300:
                return 0
            data = resp.json()
            return int(data[0]["consecutive_failures"]) if data else 0
        except Exception:
            return 0

    def record_health(self, feed: str, *, ok: bool, rows: int = 0,
                      note: str = "") -> None:
        """Publish whether this feed is alive.

        The app refuses to show appointment times unless this row is recent, so
        without it every card reads "Live times unavailable" — a gateway that
        works perfectly but says nothing is indistinguishable from a dead one.

        `note` is an error CLASS name only, never a message: upstream messages
        can quote page content.
        """
        if not self.configured:
            log(step="health", status="skipped", reason="supabase_not_configured")
            return
        import httpx

        row = {
            "feed": feed,
            "last_status": "ok" if ok else "failed",
            "last_row_count": rows,
            "note": note[:80],
        }
        if ok:
            from datetime import datetime, timezone
            row["last_ok_at"] = datetime.now(timezone.utc).isoformat()
            row["consecutive_failures"] = 0
        else:
            # Advance the failure counter so the app's fast-fail guard
            # (consecutive_failures >= 3) can actually fire. Without this the
            # field stayed at 0 forever and the guard was dead code — the
            # 20-minute staleness rule was doing all the work. A read then write
            # is fine here: this path runs only on failure, and the gateway is a
            # single instance so there is no concurrent writer to race.
            prev = self._current_failures(feed)
            row["consecutive_failures"] = prev + 1

        headers = {
            "apikey": self._key.reveal(),
            "Authorization": f"Bearer {self._key.reveal()}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        try:
            with httpx.Client(timeout=20) as client:
                client.post(f"{self._url.rstrip('/')}/rest/v1/gateway_health",
                            json=[row], params={"on_conflict": "feed"}, headers=headers)
            log(step="health", status="ok" if ok else "recorded_failure")
        except Exception:
            # Never let health reporting take down the feed it reports on.
            log(step="health", status="write_failed")

    def _write_local(self, table: str, rows: Sequence[dict[str, Any]]) -> int:
        """Fallback for local testing: write the rows to a JSON file.

        This exists so the whole pipeline can be run and inspected without
        provisioning anything and without touching the live database. Only the
        public, credential-free lane should ever reach this path — see the
        assertion below.
        """
        import json

        # Belt and braces: if an authenticated feed ever ends up here, fail
        # loudly rather than quietly dropping practice data onto a laptop disk.
        if table not in ("clinician_availability",):
            raise RuntimeError(
                f"Refusing to write table {table!r} to local disk. Only public, "
                "non-PHI output may be written locally; configure Supabase."
            )

        self._local_dir.mkdir(parents=True, exist_ok=True)
        path = self._local_dir / f"{table}.json"
        path.write_text(json.dumps(list(rows), indent=1), encoding="utf-8")
        log(step="sink", status="local_file", rows=len(rows))
        return len(rows)
