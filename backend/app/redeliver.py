"""Ask GitHub to resend webhooks that never reached us.

GitHub waits 10 seconds for a webhook reply and never retries on its own. On a free host that
sleeps when idle, the request that wakes the server can time out, so that event would be lost.
This sweep runs shortly after startup and then every few minutes: it lists the App's recent
deliveries, finds the ones that failed and that we have no record of, and asks GitHub to send
them again.

Usage (from the backend folder):  python -m app.redeliver     # one sweep, then exit
"""
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
import psycopg

from app import config
from app.github_client import API, HEADERS, _app_jwt, _check
from app.jobs import prune_old_events, retry_failed_jobs

LOOKBACK = timedelta(hours=6)  # only recent events; older ones are no longer worth acting on
MAX_PER_SWEEP = 20


def choose_redeliveries(deliveries: list[dict], known_guids: set[str], now: datetime) -> list[dict]:
    """Failed deliveries within LOOKBACK that we never stored and that never later succeeded; one per event."""
    succeeded = {d["guid"] for d in deliveries if 200 <= (d.get("status_code") or 0) < 300}
    chosen: dict[str, dict] = {}
    for d in deliveries:
        guid = d["guid"]
        delivered_at = datetime.fromisoformat(d["delivered_at"].replace("Z", "+00:00"))
        if (
            guid in known_guids
            or guid in succeeded
            or guid in chosen
            or now - delivered_at > LOOKBACK
        ):
            continue
        chosen[guid] = d
    return list(chosen.values())[:MAX_PER_SWEEP]


def _recent_deliveries(headers: dict) -> list[dict]:
    response = httpx.get(f"{API}/app/hook/deliveries", headers=headers, params={"per_page": 100})
    _check(response)
    return response.json()


def _known_guids(guids: list[str]) -> set[str]:
    if not guids:
        return set()
    with psycopg.connect(config.DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT delivery_id FROM webhook_events WHERE delivery_id = ANY(%s)", (guids,)
        ).fetchall()
    return {r[0] for r in rows}


def sweep() -> int:
    """One pass; returns how many deliveries were requested again."""
    headers = {**HEADERS, "Authorization": f"Bearer {_app_jwt()}"}
    deliveries = _recent_deliveries(headers)
    known = _known_guids([d["guid"] for d in deliveries])
    missed = choose_redeliveries(deliveries, known, datetime.now(timezone.utc))
    for d in missed:
        response = httpx.post(f"{API}/app/hook/deliveries/{d['id']}/attempts", headers=headers)
        _check(response)
        print(f"[redeliver] asked GitHub to resend {d['event']} {d.get('action') or ''} ({d['guid']})", flush=True)
    return len(missed)


def start_background_sweeps() -> None:
    """Every few minutes (first after 30s, so GitHub has marked any timeout as failed): ask GitHub to resend
    webhooks we never received, and re-run jobs that failed or were cut off."""
    interval = config.REDELIVERY_SWEEP_SECONDS
    if interval <= 0:
        return

    def loop():
        time.sleep(30)
        while True:
            for name, step in (("redeliver", sweep), ("retry", retry_failed_jobs), ("prune", prune_old_events)):
                try:
                    step()
                except Exception as error:  # never let one bad pass kill the loop
                    print(f"[{name}] pass failed: {error}", flush=True)
            time.sleep(interval)

    threading.Thread(target=loop, name="redeliver", daemon=True).start()


if __name__ == "__main__":
    print(f"requested {sweep()} redelivery(ies)")
