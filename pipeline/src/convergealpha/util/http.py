"""Polite HTTP: per-host rate limits, retries with backoff, and secret-free error messages."""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from convergealpha.util.log import redact


class RateLimiter:
    """At most `per_second` calls, shared across threads."""

    def __init__(self, per_second: float) -> None:
        self.interval = 1.0 / per_second
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.interval
        if delay > 0:
            time.sleep(delay)


# SEC asks for at most 10 requests/second; stay a little below.
_LIMITS: dict[str, RateLimiter] = {
    "www.sec.gov": RateLimiter(8),
    "data.sec.gov": RateLimiter(8),
    "efts.sec.gov": RateLimiter(8),
    "finnhub.io": RateLimiter(0.9),  # free tier: 60 calls/minute
    "api.stlouisfed.org": RateLimiter(2),
    "cdn.finra.org": RateLimiter(4),
    "api.finra.org": RateLimiter(2),
}


class HttpError(RuntimeError):
    """A request failed; the message never contains secrets (URLs are redacted)."""


def make_session(headers: Mapping[str, str] | None = None, retries: int = 4) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD", "POST"),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    if headers:
        s.headers.update(headers)
    return s


def get(
    session: requests.Session,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    timeout: float = 60,
    ok_404: bool = False,
    stream: bool = False,
) -> requests.Response | None:
    """GET with the host's rate limit. Returns None on 404 when ok_404, raises HttpError otherwise."""
    limiter = _LIMITS.get(urlparse(url).hostname or "")
    if limiter:
        limiter.wait()
    try:
        r = session.get(url, params=params, timeout=timeout, stream=stream)
    except requests.RequestException as e:
        raise HttpError(redact(f"{type(e).__name__}: {e}")) from None
    if r.status_code == 404 and ok_404:
        return None
    if r.status_code >= 400:
        raise HttpError(
            redact(f"HTTP {r.status_code} for {urlparse(url).hostname}{urlparse(url).path}")
        )
    return r
