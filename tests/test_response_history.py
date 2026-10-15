"""Habr response history must be complete before cross-source dedup."""
import unittest
from types import SimpleNamespace

from habr_career_mcp.response_history import ResponseHistoryError, get_response_history


def history(*ids, active=None, deleted=0, next_page=None, show_table=True):
    active = len(ids) if active is None else active
    main = (
        f'<a href="/responses"><div>Основные ({active})</div></a>'
        f'<a href="/responses/deleted"><div>Удалённые ({deleted})</div></a>'
    )
    table = (
        '<table class="my_responses">'
        + "".join(
            f'<tr><td><div class="title"><a href="/vacancies/{i}">Role {i}</a></div></td></tr>'
            for i in ids
        )
        + '</table>'
    ) if show_table else ''
    pager = (
        f'<div class="pagination"><a href="/responses?page={next_page}">{next_page}</a></div>'
        if next_page else ''
    )
    return '<html><body>' + main + table + pager + '</body></html>'


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.paths = []

    def get(self, path):
        self.paths.append(path)
        data = self.responses[path]
        if isinstance(data, tuple):
            status, url, body = data
        else:
            status, url, body = 200, "https://career.habr.com" + path, data
        return SimpleNamespace(status=status, url=url, text=body)


class HistoryTests(unittest.TestCase):
    def test_current_two_active_no_deleted_is_complete(self):
        c = FakeClient({
            "/responses": history(1000168944, 1000166153),
            "/responses/deleted": history(active=2, deleted=0, show_table=False),
        })
        result = get_response_history(c)
        self.assertTrue(result["history_complete"])
        self.assertEqual(result["active_count"], 2)
        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["tab_counts"], {"active": 2, "deleted": 0})
        self.assertEqual(
            [x["vacancy_id"] for x in result["responses"]],
            ["1000168944", "1000166153"],
        )
        self.assertTrue(all(not x["deleted"] for x in result["responses"]))

    def test_deleted_ids_survive_exact_dedup(self):
        c = FakeClient({
            "/responses": history(100, active=1, deleted=2),
            "/responses/deleted": history(100, 200, active=1, deleted=2),
        })
        r = get_response_history(c)
        self.assertEqual(r["active_count"], 1)
        self.assertEqual(r["deleted_count"], 2)
        self.assertEqual(len(r["responses"]), 3)
        self.assertEqual(
            {(x["vacancy_id"], x["deleted"]) for x in r["responses"]},
            {("100", False), ("100", True), ("200", True)},
        )

    def test_pagination_follows_next_and_verifies_count(self):
        c = FakeClient({
            "/responses": history(1, 2, active=3, next_page=2),
            "/responses?page=2": history(3, active=3),
            "/responses/deleted": history(active=3, deleted=0, show_table=False),
        })
        r = get_response_history(c)
        self.assertEqual(r["active_pages"], 2)
        self.assertEqual(r["active_count"], 3)
        self.assertEqual(r["deleted_count"], 0)

    def test_missing_extra_page_fails_closed(self):
        c = FakeClient({"/responses": history(1, active=5)})
        with self.assertRaisesRegex(ResponseHistoryError, "1 of 5"):
            get_response_history(c)

    def test_not_authenticated_redirect_fails_closed(self):
        c = FakeClient({
            "/responses": (200, "https://career.habr.com/users/auth_required", ""),
        })
        with self.assertRaisesRegex(ResponseHistoryError, "redirected"):
            get_response_history(c)

    def test_server_error_fails_closed(self):
        c = FakeClient({
            "/responses": (503, "https://career.habr.com/responses", ""),
        })
        with self.assertRaisesRegex(ResponseHistoryError, "HTTP 503"):
            get_response_history(c)

    def test_deleted_tab_unavailable_fails_closed(self):
        c = FakeClient({"/responses": (
            '<a href="/responses">Основные (2)</a>'
            '<table class="my_responses"></table>'
        )})
        with self.assertRaisesRegex(ResponseHistoryError, "tab counts"):
            get_response_history(c)

    def test_bounded_active_read_not_marked_complete(self):
        c = FakeClient({"/responses": history(1, active=1, deleted=4)})
        result = get_response_history(c, include_deleted=False)
        self.assertFalse(result["history_complete"])
        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["tab_counts"]["deleted"], 4)


if __name__ == "__main__":
    unittest.main()
