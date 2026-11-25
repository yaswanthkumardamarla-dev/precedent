"""Who is asking, and which repositories they may see.

The dashboard's server forwards the signed-in person's GitHub user token (from "Sign in with GitHub").
We ask GitHub which repositories that person can reach through Precedent's installations, so access
follows GitHub's own permissions. Without a token, the visitor gets the read-only public demo.
"""
import hashlib
import threading
import time
from dataclasses import dataclass

import httpx
from fastapi import Header, HTTPException

from app import config
from app.github_client import API, HEADERS

CACHE_SECONDS = 300  # how long a person's repository list is reused before asking GitHub again


@dataclass(frozen=True)
class Repo:
    name: str  # OWNER/REPO
    private: bool
    can_write: bool  # may accept or retire decisions


@dataclass(frozen=True)
class Viewer:
    login: str | None  # None for the public demo
    repos: tuple[Repo, ...]

    @property
    def is_demo(self) -> bool:
        return self.login is None

    @property
    def names(self) -> list[str]:
        return [r.name for r in self.repos]

    def can_write(self, repo: str) -> bool:
        return any(r.name == repo and r.can_write for r in self.repos)


def demo_viewer() -> Viewer:
    return Viewer(login=None, repos=tuple(Repo(name, private=False, can_write=False) for name in config.DEMO_REPOS))


_cache: dict[str, tuple[float, Viewer]] = {}
_cache_lock = threading.Lock()


def _get(path: str, token: str, params: dict | None = None) -> dict | list:
    response = httpx.get(f"{API}{path}", headers={**HEADERS, "Authorization": f"Bearer {token}"}, params=params)
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="GitHub sign-in expired")
    response.raise_for_status()
    return response.json()


def _paged(path: str, token: str, key: str) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        data = _get(path, token, {"per_page": 100, "page": page})
        items.extend(data[key])
        if len(items) >= data.get("total_count", 0) or not data[key]:
            return items
        page += 1


def lookup_viewer(token: str) -> Viewer:
    """Ask GitHub who owns this token and which repos they can reach through Precedent's installations."""
    login = _get("/user", token)["login"]
    repos: dict[str, Repo] = {}
    for installation in _paged("/user/installations", token, "installations"):
        for r in _paged(f"/user/installations/{installation['id']}/repositories", token, "repositories"):
            perms = r.get("permissions") or {}
            repos[r["full_name"]] = Repo(
                name=r["full_name"],
                private=bool(r.get("private")),
                can_write=bool(perms.get("admin") or perms.get("maintain") or perms.get("push")),
            )
    return Viewer(login=login, repos=tuple(sorted(repos.values(), key=lambda r: r.name.lower())))


def viewer_for(token: str | None, refresh: bool = False) -> Viewer:
    if not token:
        return demo_viewer()
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] > now and not refresh:
            return cached[1]
    viewer = lookup_viewer(token)
    with _cache_lock:
        _cache[key] = (now + CACHE_SECONDS, viewer)
        for stale in [k for k, (expires, _) in _cache.items() if expires <= now]:
            del _cache[stale]
    return viewer


def current_viewer(x_github_token: str | None = Header(None)) -> Viewer:
    """FastAPI dependency: the person behind this request, or the public demo."""
    return viewer_for(x_github_token)
