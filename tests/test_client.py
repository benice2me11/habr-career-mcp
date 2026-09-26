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
