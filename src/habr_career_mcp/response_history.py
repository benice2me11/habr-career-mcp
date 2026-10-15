"""Fail-closed, read-only Career Habr response-history ID collection.

Keep this separate from vacancy discovery. Deleted responses are still prior
applications and must participate in exact-ID deduplication.
"""

from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urlparse

BASE = "https://career.habr.com"
_IDS = re.compile(r"^/vacancies/(\d+)/?$")
_COUNTS = re.compile(r"\(\s*(\d[\d\s\u00a0]*)\s*\)")


class ResponseHistoryError(RuntimeError):
    """Never turn an inaccessible or partial response history into an empty set."""


class _HistoryPage(HTMLParser):
    def __init__(self, path: str):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.in_history_table = False
        self.ids: list[str] = []
        self.tab_counts: dict[str, int] = {}
        self._anchor: dict | None = None
        self.pages: dict[int, str] = {}
        self.table_seen = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and "my_responses" in (a.get("class") or "").split():
            self.in_history_table = True
            self.table_seen = True
        if tag != "a":
            return
        href = a.get("href") or ""
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != "career.habr.com":
            return
        if self.in_history_table:
            match = _IDS.fullmatch(parsed.path)
            if match:
                self.ids.append(match.group(1))
        if parsed.path in ("/responses", "/responses/deleted"):
            self._anchor = {"path": parsed.path, "parts": []}
            if parsed.path == self.path:
                raw_page = parse_qs(parsed.query).get("page", [None])[0]
                if raw_page is not None:
                    try:
                        number = int(raw_page)
                    except (TypeError, ValueError):
                        return
                    if number >= 1:
                        self.pages[number] = href

    def handle_data(self, data):
        if self._anchor is not None:
            self._anchor["parts"].append(data)

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_history_table = False
        if tag == "a" and self._anchor is not None:
            label = " ".join("".join(self._anchor["parts"]).split())
            match = _COUNTS.search(label)
            if match:
                key = "deleted" if self._anchor["path"] == "/responses/deleted" else "active"
                self.tab_counts[key] = int(re.sub(r"\D", "", match.group(1)))
            self._anchor = None


def _read_page(client, path: str, page_number: int):
    response = client.get(path)
    if response.status != 200:
        raise ResponseHistoryError(
            f"Habr response history returned HTTP {response.status}; history incomplete"
        )
    url = urlparse(response.url)
    expected_path = urlparse(path).path
    if url.scheme != "https" or url.netloc != "career.habr.com" or url.path != expected_path:
        raise ResponseHistoryError(
            "Habr response history redirected to login/other location; history incomplete"
        )
    actual = parse_qs(url.query).get("page", ["1"])[0]
    if str(page_number) != actual:
        raise ResponseHistoryError(
            f"Habr response history page {page_number} clamped to {actual}; history incomplete"
        )
    parser = _HistoryPage(expected_path)
    parser.feed(response.text)
    parser.close()
    return parser


def _collect_tab(client, path: str, expected: int):
    seen: set[str] = set()
    records: list[str] = []
    page_number = 1
    page_path = path
    while page_number <= 100:
        doc = _read_page(client, page_path, page_number)
        if not doc.table_seen and expected > 0:
            raise ResponseHistoryError(
                f"Habr {path} has no response table; history incomplete"
            )
        for vacancy_id in doc.ids:
            if vacancy_id not in seen:
                seen.add(vacancy_id)
                records.append(vacancy_id)
        if len(seen) > expected:
            raise ResponseHistoryError(
                f"Habr {path} returned more distinct response IDs than tab count; history incomplete"
            )
        further = sorted(n for n in doc.pages if n > page_number)
        if len(seen) == expected:
            if further:
                raise ResponseHistoryError(
                    f"Habr {path} lists another response page after expected count; history incomplete"
                )
            return records, page_number
        if not further:
            raise ResponseHistoryError(
                f"Habr {path} has {len(seen)} of {expected} response IDs; history incomplete"
            )
        if further[0] != page_number + 1:
            raise ResponseHistoryError(
                f"Habr {path} skipped response page {page_number + 1}; history incomplete"
            )
        page_number += 1
        page_path = doc.pages[page_number]
    raise ResponseHistoryError(f"Habr {path} exceeded 100 pages; history incomplete")


def get_response_history(client, *, include_deleted=True):
    """Return exact applied vacancy IDs or raise; never return partial success."""
    main = _read_page(client, "/responses", 1)
    if "active" not in main.tab_counts or "deleted" not in main.tab_counts:
        raise ResponseHistoryError("Habr response tab counts unavailable; history incomplete")
    counts = {"active": main.tab_counts["active"], "deleted": main.tab_counts["deleted"]}
    active, active_pages = _collect_tab(client, "/responses", counts["active"])
    deleted: list[str] = []
    deleted_pages = 0
    if include_deleted:
        deleted, deleted_pages = _collect_tab(
            client, "/responses/deleted", counts["deleted"]
        )
    responses = [
        {"vacancy_id": vid, "vacancy_url": f"{BASE}/vacancies/{vid}", "deleted": flag}
        for vids, flag in ((active, False), (deleted, True))
        for vid in vids
    ]
    return {
        "source": "habr_career",
        "responses": responses,
        "active_count": len(active),
        "deleted_count": len(deleted),
        "tab_counts": counts,
        "active_pages": active_pages,
        "deleted_pages": deleted_pages,
        "history_complete": bool(include_deleted),
    }
