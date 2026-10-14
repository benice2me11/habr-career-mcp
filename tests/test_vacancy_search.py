"""Structured vacancy discovery stays read-only and never truncates HTML before parsing."""
import unittest
from types import SimpleNamespace

from habr_career_mcp.vacancy_search import parse_listing, search_vacancies


def card(i, shuffled=False, missing=False):
    anchor = (
        f'href="/vacancies/{i}" class="vacancy-card__backdrop-link"'
        if shuffled else
        f'class="vacancy-card__backdrop-link" href="/vacancies/{i}"'
    )
    return (
        f'<div class="vacancy-card"><a {anchor}></a>'
        f'<div class="vacancy-card__info">'
        f'<a href="/companies/test">Employer {i}</a>'
        f'<a class="vacancy-card__title-link" href="/vacancies/{i}">Role {i}</a>'
        f'<div class="vacancy-card__salary">'
        f'{"Зарплата не указана" if missing else "от 300000 ₽"}</div>'
        f'<time datetime="2026-10-14T14:00:00+03:00">Today</time></div></div>'
    )


class SearchTests(unittest.TestCase):
    def test_full_html_more_than_100k_returns_fifteen_distinct_cards(self):
        html = (
            '<div data-vacancy-list="">'
            + ('x' * 120000)
            + ''.join(card(i, shuffled=i % 2 == 0) for i in range(15))
            + '<nav class="pagination"><a href="/vacancies?q=Fullstack&page=2">'
            + 'Next</a></nav></div>'
        )
        r = parse_listing(html, query="Fullstack", page=1, limit=50)
        self.assertEqual(r["unique_page_count"], 15)
        self.assertEqual(len({x["vacancy_id"] for x in r["vacancies"]}), 15)
        self.assertEqual(r["next_page"], 2)
        self.assertFalse(r["search_complete"])
        self.assertEqual(r["vacancies"][0]["employer"], "Employer 0")
        self.assertEqual(r["vacancies"][0]["published_at"], "2026-10-14T14:00:00+03:00")

    def test_predicted_salary_is_not_employer_compensation(self):
        r = parse_listing(
            '<div data-vacancy-list="">' + card(1, missing=True) + '</div>',
            query="",
        )
        self.assertIsNone(r["vacancies"][0]["salary_raw"])
        self.assertFalse(r["search_complete"])
        self.assertEqual(r["stop_reason"], "pagination_unverified")

    def test_explicit_truncated_response_rejected(self):
        with self.assertRaises(ValueError):
            parse_listing(
                '<div data-vacancy-list>...[truncated, 400000 chars total]',
                query="",
            )

    def test_http_failure_is_not_empty_results(self):
        class BrokenClient:
            def get(self, path):
                return SimpleNamespace(
                    status=503,
                    url="https://career.habr.com/vacancies",
                    text="",
                )
        with self.assertRaises(RuntimeError):
            search_vacancies(BrokenClient(), "Go")

    def test_response_limit_does_not_claim_complete_page(self):
        r = parse_listing(
            '<div data-vacancy-list="">' + card(1) + card(2) + '</div>',
            query="", limit=1,
        )
        self.assertEqual(r["returned_count"], 1)
        self.assertFalse(r["page_complete"])

    def test_explicit_empty_result(self):
        r = parse_listing(
            '<div data-vacancy-list="">Ничего не найдено</div>',
            query="foo",
        )
        self.assertTrue(r["search_complete"])
        self.assertEqual(r["vacancies"], [])


if __name__ == "__main__":
    unittest.main()
