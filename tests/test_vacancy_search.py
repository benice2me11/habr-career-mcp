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



    def test_footer_card_ignored_even_when_other_cards_present(self):
        result = parse_listing(
            '<div data-vacancy-list="">' + card(1) + '</div>' + card(999),
            query="",
        )
        self.assertEqual([c["vacancy_id"] for c in result["vacancies"]], ["1"])

    def test_duplicate_cards_are_deduplicated(self):
        result = parse_listing(
            '<div data-vacancy-list="">' + card(1) + card(1) + '</div>',
            query="",
        )
        self.assertEqual(result["unique_page_count"], 1)

    def test_unrelated_pagination_does_not_claim_exhaustion(self):
        html = (
            '<nav class="pagination"><a href="/blog?page=2">Next</a></nav>'
            '<div data-vacancy-list="">' + card(1) + '</div>'
        )
        result = parse_listing(html, query="")
        self.assertFalse(result["search_complete"])
        self.assertFalse(result["pagination_verified"])

    def test_unresolvable_next_control_cannot_claim_exhaustion(self):
        html = (
            '<div data-vacancy-list="">' + card(1)
            + '<nav class="pagination"><a rel="next" '
            'href="/vacancies?type=all&q=Go">Next</a></nav></div>'
        )
        result = parse_listing(html, query="Go")
        self.assertFalse(result["search_complete"])
        self.assertEqual(result["stop_reason"], "unresolved_next_page")

    def test_final_page_with_previous_numeric_page_is_verified(self):
        html = (
            '<div data-vacancy-list="">' + card(1)
            + '<nav class="pagination"><a '
            'href="/vacancies?type=all&q=Go&page=1">1</a></nav></div>'
        )
        self.assertTrue(parse_listing(html, query="Go", page=2)["search_complete"])

    def test_redirected_page_is_error(self):
        class Changed:
            def get(self, path):
                return SimpleNamespace(
                    status=200,
                    url="https://career.habr.com/vacancies?q=Go&type=all&page=1",
                    text='<div data-vacancy-list=""></div>',
                )
        with self.assertRaisesRegex(RuntimeError, "redirected/clamped"):
            search_vacancies(Changed(), "Go", page=2)

    def test_query_mismatch_is_error(self):
        class Changed:
            def get(self, path):
                return SimpleNamespace(
                    status=200,
                    url="https://career.habr.com/vacancies?q=Python&type=all&page=1",
                    text='<div data-vacancy-list=""></div>',
                )
        with self.assertRaisesRegex(RuntimeError, "changed query"):
            search_vacancies(Changed(), "Go")

    def test_identical_repeated_page_fails_closed(self):
        html = '<div data-vacancy-list="">' + card(10) + '</div>'
        first = parse_listing(html, query="Go", page=1)
        class Same:
            def get(self, path):
                return SimpleNamespace(
                    status=200,
                    url="https://career.habr.com/vacancies?type=all&q=Go&page=2",
                    text=html,
                )
        with self.assertRaisesRegex(RuntimeError, "repeated"):
            search_vacancies(
                Same(), "Go", page=2,
                previous_page_fingerprint=first["page_fingerprint"],
            )

    def test_empty_query_url_is_supported(self):
        html = '<div data-vacancy-list="">' + card(1) + '</div>'
        class Home:
            def get(self, path):
                return SimpleNamespace(
                    status=200,
                    url="https://career.habr.com/vacancies?type=all&q=&page=1",
                    text=html,
                )
        self.assertEqual(search_vacancies(Home(), "")["unique_page_count"], 1)


if __name__ == "__main__":
    unittest.main()
