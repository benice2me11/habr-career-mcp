import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, build_opener

BASE_URL = "https://career.habr.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class Response:
    status: int
    url: str
    text: str


def normalize_cookie(value: str) -> str:
    value = value.strip()
    if value and "=" not in value:
        return "_career_session=" + value
    return value


def extract_csrf(page: str) -> str:
    match = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)', page, re.I)
    if not match:
        match = re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+name=["\']csrf-token["\']', page, re.I)
    if not match:
        raise RuntimeError("csrf-token not found; session may be invalid or WAF page was returned")
    return match.group(1)


def encode_pairs(fields: Iterable[Tuple[str, str]]) -> str:
    return urlencode(list(fields), doseq=True, encoding="utf-8")


def _read_cookie_from_env() -> str:
    cookie = os.environ.get("HABR_COOKIE", "")
    if cookie.strip():
        return normalize_cookie(cookie)
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("HABR_COOKIE="):
                return normalize_cookie(line.split("=", 1)[1].strip().strip("'\""))
    try:
        from .auth import cookie_header_from_state
        return normalize_cookie(cookie_header_from_state())
    except (OSError, ValueError, KeyError):
        return ""


class HabrClient:
    def __init__(self, cookie: Optional[str] = None, base_url: str = BASE_URL, opener=None):
        self.base_url = base_url.rstrip("/") + "/"
        self.cookie = normalize_cookie(cookie if cookie is not None else _read_cookie_from_env())
        self.opener = opener or build_opener()
        self._csrf: Optional[str] = None

    def _request(self, path: str, method: str = "GET", body: Optional[bytes] = None, extra_headers=None) -> Response:
        url = urljoin(self.base_url, path.lstrip("/"))
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "ru,en;q=0.9",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        if extra_headers:
            headers.update(extra_headers)
        req = Request(url, data=body, method=method.upper(), headers=headers)
        try:
            with self.opener.open(req, timeout=30) as res:
                raw = res.read()
                return Response(res.status, res.geturl(), raw.decode("utf-8", errors="replace"))
        except HTTPError as exc:
            raw = exc.read()
            return Response(exc.code, exc.geturl(), raw.decode("utf-8", errors="replace"))

    def get_text(self, path: str) -> str:
        response = self._request(path)
        if response.status >= 400:
            raise RuntimeError(f"GET {path} failed with HTTP {response.status}")
        return response.text

    def get(self, path: str) -> Response:
        return self._request(path)

    def csrf(self) -> str:
        if self._csrf is None:
            self._csrf = extract_csrf(self.get_text("/"))
        return self._csrf

    def submit(self, action: str, method: str, fields) -> Response:
        clean = [(k, v) for k, v in fields if k not in ("authenticity_token", "_method")]
        body = encode_pairs(clean).encode("utf-8")

        def send() -> Response:
            return self._request(
                action,
                method=method,
                body=body,
                extra_headers={
                    "X-CSRF-Token": self.csrf(),
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": urljoin(self.base_url, action.lstrip("/")),
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
            )

        response = send()
        if response.status == 422:
            self._csrf = None
            response = send()
        return response
