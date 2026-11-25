"""Talking to GitHub's API as the Precedent GitHub App."""
import time

import httpx
import jwt

from app import config

API = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _check(response: httpx.Response) -> None:
    """Raise an error that includes GitHub's own explanation, not just the status code."""
    if response.is_success:
        return
    try:
        reason = response.json().get("message", response.text)
    except ValueError:
        reason = response.text
    raise RuntimeError(
        f"GitHub returned {response.status_code} for {response.request.url}\n"
        f"GitHub says: {reason}"
    )


def _app_jwt() -> str:
    """A short-lived token, signed with the App's private key, proving we are the App."""
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 540,
        "iss": config.GITHUB_CLIENT_ID,
    }
    return jwt.encode(payload, config.github_private_key(), algorithm="RS256")


def installation_token(repo: str) -> str:
    """Exchange the App token for a token that can work on one repo the App is installed on."""
    headers = {**HEADERS, "Authorization": f"Bearer {_app_jwt()}"}

    response = httpx.get(f"{API}/repos/{repo}/installation", headers=headers)
    _check(response)
    installation_id = response.json()["id"]

    response = httpx.post(
        f"{API}/app/installations/{installation_id}/access_tokens", headers=headers
    )
    _check(response)
    return response.json()["token"]


def _auth(token: str) -> dict:
    return {**HEADERS, "Authorization": f"Bearer {token}"}


def _get_all(url: str, token: str) -> list[dict]:
    """GET a list endpoint and follow GitHub's pagination until every item is fetched."""
    items: list[dict] = []
    params = {"per_page": 100}
    while url:
        response = httpx.get(url, headers=_auth(token), params=params)
        _check(response)
        items.extend(response.json())
        url = response.links.get("next", {}).get("url")
        params = None  # the "next" URL already contains the paging parameters
    return items


def _humans_only(items: list[dict]) -> list[dict]:
    """Drop comments written by bots, including Precedent's own comments."""
    return [item for item in items if (item.get("user") or {}).get("type") != "Bot"]


def fetch_pr_discussion(repo: str, number: int, token: str) -> dict:
    """Everything people said on a pull request."""
    base = f"{API}/repos/{repo}"
    return {
        "review_comments": _humans_only(_get_all(f"{base}/pulls/{number}/comments", token)),
        "issue_comments": _humans_only(_get_all(f"{base}/issues/{number}/comments", token)),
        "reviews": _humans_only(_get_all(f"{base}/pulls/{number}/reviews", token)),
    }


def fetch_pr(repo: str, number: int, token: str) -> dict:
    """A pull request's title, description and other details."""
    response = httpx.get(f"{API}/repos/{repo}/pulls/{number}", headers=_auth(token))
    _check(response)
    return response.json()


def fetch_pr_files(repo: str, number: int, token: str) -> list[dict]:
    """The files a pull request changes, each with its diff ("patch")."""
    return _get_all(f"{API}/repos/{repo}/pulls/{number}/files", token)


def upsert_pr_comment(
    repo: str, number: int, token: str, body: str, marker: str, create: bool = True
) -> str | None:
    """Edit Precedent's existing comment on the PR, or create one if there isn't one yet.

    The marker is a hidden HTML comment inside the body, so we can find our own
    comment again and update it instead of posting a new one on every run.
    Returns the comment's URL, or None if nothing was posted.
    """
    comments = _get_all(f"{API}/repos/{repo}/issues/{number}/comments", token)
    ours = [
        c for c in comments
        if marker in (c.get("body") or "") and (c.get("user") or {}).get("type") == "Bot"
    ]
    if ours:
        response = httpx.patch(
            f"{API}/repos/{repo}/issues/comments/{ours[0]['id']}",
            headers=_auth(token),
            json={"body": body},
        )
    elif create:
        response = httpx.post(
            f"{API}/repos/{repo}/issues/{number}/comments",
            headers=_auth(token),
            json={"body": body},
        )
    else:
        return None
    _check(response)
    return response.json()["html_url"]