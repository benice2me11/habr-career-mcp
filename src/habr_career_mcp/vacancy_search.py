"""Read-only Habr Career discovery from a complete, untruncated HTML page.

A listing may be marked incomplete, but never silently treated as exhaustive.
"""
from html.parser import HTMLParser
import hashlib
import re
from urllib.parse import parse_qs, urlencode, urlparse

BASE = "https://career.habr.com"
_VACANCY = re.compile(r"^/vacancies/(\d+)/?$", re.I)
_COMPANY = re.compile(r"^/companies/[^/]+/?$", re.I)
_EMPTY_MARKERS = ("ничего не найдено", "вакансии не найдены", "по вашему запросу ничего")


def _clean(value):
    return " ".join(value.split()) or None


class _Cards(HTMLParser):
    def __init__(self, query):
        super().__init__(convert_charrefs=True)
        self.query = query
        self.divs = []
        self.list_depth = None
        self.saw_listing = False
        self.cards = []
        self.current = None
        self.card_level = None
        self.capture = None
        self.capture_buffer = []
        self.salary_bits = []
        self.pages = set()
        self.saw_pagination = False
        self.unknown_next = False
        self.empty_text = []

    def _href_is_listing(self, href):
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != "career.habr.com":
            return False, parsed
        if parsed.path.rstrip("/") != "/vacancies":
            return False, parsed
        params = parse_qs(parsed.query)
        if "q" in params and params["q"] != [self.query]:
            return False, parsed
        if "type" in params and params["type"] != ["all"]:
            return False, parsed
        return True, parsed

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag == "div":
            self.divs.append(classes)
            if "data-vacancy-list" in attrs:
                self.saw_listing = True
                self.list_depth = len(self.divs)
            if self.list_depth is not None and "vacancy-card" in classes and self.current is None:
                self.current = {
                    "vacancy_id": None, "title": None, "employer": None,
                    "salary_raw": None, "published_at": None,
                }
                self.card_level = len(self.divs)
                self.salary_bits = []

        if self.list_depth is not None and any("pagination" in c or "pager" in c for c in classes):
            self.saw_pagination = True
        if tag != "a":
            if tag == "time" and self.current is not None and attrs.get("datetime"):
                self.current["published_at"] = attrs["datetime"]
            return

        href = attrs.get("href") or ""
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != "career.habr.com":
            return
        if self.current is not None:
            match = _VACANCY.fullmatch(parsed.path)
            if match and not self.current["vacancy_id"]:
                self.current["vacancy_id"] = match.group(1)
            if "vacancy-card__title-link" in classes:
                self.capture = "title"
                self.capture_buffer = []
            elif _COMPANY.fullmatch(parsed.path) and self.current["employer"] is None:
                self.capture = "employer"
                self.capture_buffer = []
        elif self.list_depth is not None:
            eligible, parsed = self._href_is_listing(href)
            if not eligible:
                return
            params = parse_qs(parsed.query)
            rel_next = "next" in (attrs.get("rel") or "").split()
            raw_page = params.get("page", [None])[0]
            if raw_page is not None:
                try:
                    page = int(raw_page)
                except (TypeError, ValueError):
                    if rel_next:
                        self.unknown_next = True
                    return
                if page > 0:
                    self.pages.add(page)
                    self.saw_pagination = True
                elif rel_next:
                    self.unknown_next = True
            elif rel_next:
                self.unknown_next = True
                self.saw_pagination = True

    def handle_data(self, data):
        if self.current is not None:
            if self.capture is not None:
                self.capture_buffer.append(data)
            if any("vacancy-card__salary" in c for c in self.divs):
                self.salary_bits.append(data)
        elif self.list_depth is not None and data.strip() and len(self.empty_text) < 300:
            self.empty_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.capture is not None and self.current is not None:
            value = _clean("".join(self.capture_buffer))
            if value:
                self.current[self.capture] = value
            self.capture = None
            self.capture_buffer = []
        if tag == "div" and self.divs:
            self.divs.pop()
            if self.current is not None and len(self.divs) < self.card_level:
                raw = _clean(" ".join(self.salary_bits))
                self.current["salary_raw"] = (
                    None if raw and "зарплата не указана" in raw.lower() else raw
                )
                if self.current["vacancy_id"] and self.current["title"]:
                    self.current["canonical_url"] = (
                        f"{BASE}/vacancies/{self.current['vacancy_id']}"
                    )
                    self.cards.append(self.current)
                self.current = None
                self.card_level = None
                self.salary_bits = []
            if self.list_depth is not None and len(self.divs) < self.list_depth:
                self.list_depth = None


def parse_listing(html, *, query, page=1, limit=50, url=None):
    """Parse all source cards; mark pagination uncertainty instead of guessing."""
    if not isinstance(html, str) or not html:
        raise ValueError("Habr listing body is empty")
    if not isinstance(query, str) or len(query) > 250:
        raise ValueError("query must be text of at most 250 characters")
    if not isinstance(page, int) or not 1 <= page <= 100:
        raise ValueError("page must be 1..100")
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    if "...[truncated," in html[-120:]:
        raise ValueError("Habr listing body was truncated before parsing")
    parser = _Cards(query)
    parser.feed(html)
    parser.close()
    if not parser.saw_listing:
        raise ValueError("Habr vacancy list marker missing; login, WAF or changed markup")
    unique = {}
    for card in parser.cards:
        unique.setdefault(card["vacancy_id"], card)
    cards = list(unique.values())
    page_fingerprint = hashlib.sha256(
        ",".join(sorted(unique.keys())).encode("utf-8")
    ).hexdigest()[:16]
    empty = not cards and any(marker in " ".join(parser.empty_text).lower() for marker in _EMPTY_MARKERS)
    if not cards and not empty:
        raise ValueError("Habr vacancy cards absent without an explicit empty-state marker")
    next_pages = sorted(n for n in parser.pages if n > page)
    next_page = next_pages[0] if next_pages else None
    page_complete = len(cards) <= limit
    pagination_verified = bool(parser.pages or parser.saw_pagination or empty)
    # A rel=next link without a verified numeric page is NOT evidence of exhaustion.
    search_complete = bool(
        page_complete and not parser.unknown_next and not next_page
        and pagination_verified
    )
    return {
        "source": "habr_career", "query": query, "page": page,
        "source_url": url, "html_chars": len(html),
        "page_fingerprint": page_fingerprint,
        "vacancies": cards[:limit], "unique_page_count": len(cards),
        "returned_count": min(limit, len(cards)),
        "limit_truncated": not page_complete, "page_complete": page_complete,
        "pagination_verified": pagination_verified,
        "next_page": next_page, "search_complete": search_complete,
        "stop_reason": (
            "next_page_available" if next_page else
            "listing_limit" if not page_complete else
            "unresolved_next_page" if parser.unknown_next else
            "verified_end" if search_complete else "pagination_unverified"
        ),
    }


def search_vacancies(client, query, page=1, limit=50, previous_page_fingerprint=None):
    """GET one page; extract before response-size limits are applied."""
    if not isinstance(query, str) or len(query) > 250:
        raise ValueError("query must be text of at most 250 characters")
    if not isinstance(page, int) or not 1 <= page <= 100:
        raise ValueError("page must be 1..100")
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    path = "/vacancies?" + urlencode({"type": "all", "q": query, "page": page})
    response = client.get(path)
    if response.status != 200:
        raise RuntimeError(f"Habr vacancies returned HTTP {response.status}; page not screened")
    parsed = urlparse(response.url)
    if parsed.hostname != "career.habr.com" or parsed.path.rstrip("/") != "/vacancies":
        raise RuntimeError("Habr vacancies redirected unexpectedly; page not screened")
    params = parse_qs(parsed.query, keep_blank_values=True)
    if params.get("q", [""])[0] != query:
        raise RuntimeError("Habr vacancy search changed query in redirect; page not screened")
    actual_page = params.get("page", ["1"])[0]
    if actual_page != str(page):
        raise RuntimeError("Habr vacancy results redirected/clamped page; page not screened")
    result = parse_listing(response.text, query=query, page=page, limit=limit, url=response.url)
    if previous_page_fingerprint is not None:
        if not isinstance(previous_page_fingerprint, str):
            raise ValueError("previous_page_fingerprint must be a string")
        if page > 1 and result["page_fingerprint"] == previous_page_fingerprint:
            raise RuntimeError("Habr page repeated the previous vacancy set; coverage incomplete")
    return result
