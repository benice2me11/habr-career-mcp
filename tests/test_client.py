from habr_career_mcp.client import normalize_cookie, extract_csrf, encode_pairs


def test_normalize_cookie_accepts_full_header_or_bare_session():
    assert normalize_cookie("_career_session=abc; remember_user_token=def") == "_career_session=abc; remember_user_token=def"
    assert normalize_cookie("abc") == "_career_session=abc"
    assert normalize_cookie("") == ""


def test_extract_csrf():
    page = '<meta name="csrf-token" content="token-123">'
    assert extract_csrf(page) == "token-123"


def test_encode_pairs_preserves_duplicate_names():
    body = encode_pairs([("skills[]", "1"), ("skills[]", "2"), ("salary", "500000")])
    assert body == "skills%5B%5D=1&skills%5B%5D=2&salary=500000"


def test_cookie_header_from_playwright_state(tmp_path):
    import json
    from habr_career_mcp.auth import cookie_header_from_state

    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "cookies": [
            {"name": "_career_session", "value": "abc", "domain": "career.habr.com"},
            {"name": "remember_user_token", "value": "def", "domain": ".habr.com"},
            {"name": "other", "value": "skip", "domain": "example.com"},
        ]
    }))
    assert cookie_header_from_state(state) == "_career_session=abc; remember_user_token=def"
