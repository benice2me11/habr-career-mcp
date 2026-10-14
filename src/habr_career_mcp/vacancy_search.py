"""Read-only Career Habr listing parser; never truncate the upstream HTML."""
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse
import re

BASE = "https://career.habr.com"
_VACANCY = re.compile(r"^/vacancies/(\d+)/?$", re.I)
_COMPANY = re.compile(r"^/companies/[^/]+/?$", re.I)
_EMPTY_MARKERS = ("ничего не найдено", "вакансии не найдены", "по вашему запросу ничего")


def _clean(value):
    return " ".join(value.split()) or None


class _Cards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.divs = []
        self.cards = []
        self.current = None
        self.card_level = None
        self.capture = None
        self.capture_buffer = []
        self.salary_bits = []
        self.pages = set()
        self.saw_pagination = False
        self.saw_listing = False
        self.empty_text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        if "data-vacancy-list" in a:
            self.saw_listing = True
        if "pagination" in (a.get("class") or "") or "pager" in (a.get("class") or ""):
            self.saw_pagination = True
        if tag == "div":
            self.divs.append(classes)
            if "vacancy-card" in classes and self.current is None:
                self.current = {"vacancy_id": None, "title": None, "employer": None,
                                "salary_raw": None, "published_at": None}
                self.card_level = len(self.divs)
                self.salary_bits = []
        if tag == "a":
            href = a.get("href") or ""
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
            elif parsed.path == "/vacancies" and "page" in parse_qs(parsed.query):
                try:
                    number = int(parse_qs(parsed.query)["page"][0])
                except (ValueError, IndexError):
                    number = 0
                if number > 0:
                    self.pages.add(number)
                    self.saw_pagination = True
            if "next" in (a.get("rel") or "").split():
                self.saw_pagination = True
        if self.current is not None and tag == "time" and a.get("datetime"):
            self.current["published_at"] = a["datetime"]

    def handle_data(self, data):
        if self.current is not None:
            if self.capture is not None:
                self.capture_buffer.append(data)
            if any("vacancy-card__salary" in c for c in self.divs):
                self.salary_bits.append(data)
        else:
            if data.strip() and len(self.empty_text) < 300:
                self.empty_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.capture and self.current is not None:
            value = _clean("".join(self.capture_buffer))
            if value:
                self.current[self.capture] = value
            self.capture = None
            self.capture_buffer = []
        if tag == "div" and self.divs:
            self.divs.pop()
            if self.current is not None and len(self.divs) < self.card_level:
                raw = _clean(" ".join(self.salary_bits))
                self.current["salary_raw"] = None if raw and "зарплата не указана" in raw.lower() else raw
                if self.current["vacancy_id"] and self.current["title"]:
                    self.current["canonical_url"] = f"{BASE}/vacancies/{self.current['vacancy_id']}"
                    self.cards.append(self.current)
                self.current = None
                self.card_level = None
                self.salary_bits = []


def parse_listing(html, *, query, page=1, limit=50, url=None):
    """Parse a FULL listing body; unverified pagination stays visibly partial."""
    if not isinstance(html, str) or not html:
        raise ValueError("Habr listing body is empty")
    if not 1 <= page <= 100 or not 1 <= limit <= 100:
        raise ValueError("page and limit must be between 1 and 100")
    if "...[truncated," in html[-100:]:
        raise ValueError("Habr listing body was truncated before parsing")
    parser = _Cards()
    parser.feed(html)
    parser.close()
    if not parser.saw_listing:
        raise ValueError("Habr vacancy list marker missing; login, WAF or changed markup")
    unique = {}
    for card in parser.cards:
        unique.setdefault(card["vacancy_id"], card)
    cards = list(unique.values())
    empty = any(marker in " ".join(parser.empty_text).lower() for marker in _EMPTY_MARKERS)
    if not cards and not empty:
        raise ValueError("Habr vacancy cards absent without an explicit empty-state marker")
    next_pages = sorted(n for n in parser.pages if n > page)
    next_page = next_pages[0] if next_pages else None
    return {
        "source": "habr_career", "query": query, "page": page,
        "source_url": url, "html_chars": len(html),
        "vacancies": cards[:limit], "unique_page_count": len(cards),
        "returned_count": min(limit, len(cards)),
        "limit_truncated": len(cards) > limit,
        "page_complete": len(cards) <= limit,
        "pagination_verified": parser.saw_pagination or empty,
        "next_page": next_page,
        "search_complete": bool((parser.saw_pagination or empty) and next_page is None and len(cards) <= limit),
        "stop_reason": ("next_page_available" if next_page else
                        "listing_limit" if len(cards) > limit else
                        "verified_end" if parser.saw_pagination or empty else
                        "pagination_unverified"),
    }


def search_vacancies(client, query, page=1, limit=50):
    """GET one page, parse the untruncated authenticated response server-side."""
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
    if urlparse(response.url).netloc != "career.habr.com":
        raise RuntimeError("Habr vacancies redirected to unexpected host; page not screened")
    return parse_listing(response.text, query=query, page=page, limit=limit, url=response.url)
