"""Network checks: reachability, redirects, domain age (RDAP), repository health."""

from __future__ import annotations

import datetime as dt
import json
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from common import REPO_URL
from policy import registrable_domain

USER_AGENT = f"Mozilla/5.0 (compatible; trading-awesome-linkcheck/1.0; +{REPO_URL})"
# Statuses that usually mean "a bot wall answered", not "the page is gone".
UNVERIFIABLE_STATUSES = {401, 403, 405, 406, 409, 425, 429, 451, 503, 520, 521, 522, 523, 525, 526}


@dataclass
class FetchResult:
    url: str
    status: int | None = None
    final_url: str | None = None
    error: str | None = None
    redirects: list[str] = field(default_factory=list)
    reset: bool = False

    @property
    def ok(self) -> bool:
        return self.status is not None and self.status < 400

    @property
    def unverifiable(self) -> bool:
        # Bot walls answer with 403/429 or simply reset the connection.
        return self.status in UNVERIFIABLE_STATUSES or self.reset

    @property
    def broken(self) -> bool:
        return not self.ok and not self.unverifiable

    @property
    def moved_domain(self) -> bool:
        if not self.final_url:
            return False
        before = registrable_domain(urlsplit(self.url).hostname or "")
        after = registrable_domain(urlsplit(self.final_url).hostname or "")
        return before != after

    def describe(self) -> str:
        if self.error:
            return self.error
        return f"HTTP {self.status}"


class _RecordingRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 8

    def __init__(self) -> None:
        self.chain: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.chain.append(newurl)
        if not newurl.startswith("https://"):
            raise urllib.error.HTTPError(newurl, 599, "redirect to a non-HTTPS URL", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, timeout: float = 20.0) -> FetchResult:
    result = FetchResult(url=url)
    handler = _RecordingRedirects()
    opener = urllib.request.build_opener(handler, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en",
    })
    try:
        with opener.open(request, timeout=timeout) as resp:
            resp.read(65536)
            result.status = resp.status
            result.final_url = resp.geturl()
    except urllib.error.HTTPError as exc:
        result.status = exc.code
        result.final_url = exc.geturl() if exc.code != 599 else None
        if exc.code == 599:
            result.error = "redirects to a non-HTTPS URL"
    except ssl.SSLError as exc:
        result.error = f"TLS error: {exc.reason or exc}"
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ConnectionResetError):
            result.reset = True
            result.error = "connection reset by the server (often bot protection)"
        else:
            result.error = f"unreachable: {reason}"
    result.redirects = handler.chain
    return result


def domain_registered(domain: str) -> dt.date | None:
    """Registration date from RDAP, or None if the registry does not say."""
    request = urllib.request.Request(f"https://rdap.org/domain/{domain}", headers={
        "User-Agent": USER_AGENT, "Accept": "application/rdap+json",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, socket.timeout, TimeoutError, ValueError, OSError):
        return None
    for event in data.get("events", []):
        if event.get("eventAction") == "registration" and event.get("eventDate"):
            try:
                return dt.date.fromisoformat(event["eventDate"][:10])
            except ValueError:
                return None
    return None


def repo_health(gh, repo_url: str, *, inactive_days: int) -> list[str]:
    """Problems with a GitHub repository (archived, gone, inactive, unlicensed)."""
    parts = urlsplit(repo_url)
    full_name = "/".join([p for p in parts.path.split("/") if p][:2])
    info = gh.repo_info(full_name)
    if info is None:
        return ["repository not found"]
    problems = []
    if info.get("archived"):
        problems.append("repository is archived")
    pushed = info.get("pushed_at")
    if pushed:
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
        if age > inactive_days:
            problems.append(f"no pushes for {age} days")
    if info.get("html_url", "").lower() != f"https://github.com/{full_name}".lower():
        problems.append(f"repository moved to {info.get('html_url')}")
    return problems
