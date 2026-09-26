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


def test_request_keeps_absolute_form_action_url():
    class FakeResponse:
        status = 200
        def geturl(self):
            return "https://career.habr.com/profile/personal"
        def read(self):
            return b"ok"
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    class FakeOpener:
        def __init__(self):
            self.url = None
        def open(self, request, timeout):
            self.url = request.full_url
            return FakeResponse()

    opener = FakeOpener()
    from habr_career_mcp.client import HabrClient
    client = HabrClient(cookie="", opener=opener)
    client._request("https://career.habr.com/profile/personal")
    assert opener.url == "https://career.habr.com/profile/personal"


def test_encode_multipart_preserves_repeated_names():
    from habr_career_mcp.client import encode_multipart
    body, content_type = encode_multipart(
        [("_method", "patch"), ("skills[]", "1"), ("skills[]", "2")],
        boundary="BOUNDARY",
    )
    text = body.decode()
    assert content_type == "multipart/form-data; boundary=BOUNDARY"
    assert text.count('name="skills[]"') == 2
    assert "\r\n\r\npatch\r\n" in text


def test_submit_sends_browser_style_multipart_post():
    calls = []
    from habr_career_mcp.client import HabrClient, Response
    client = HabrClient(cookie="")
    client._csrf = "csrf"
    def fake_request(path, method="GET", body=None, extra_headers=None):
        calls.append((path, method, body, extra_headers))
        return Response(302, path, "")
    client._request = fake_request
    response = client.submit(
        "https://career.habr.com/profile/personal",
        "PATCH",
        [("_method", "patch"), ("user[about]", "hello")],
        multipart=True,
    )
    assert response.status == 302
    path, method, body, headers = calls[0]
    assert method == "POST"
    assert path == "https://career.habr.com/profile/personal"
    assert headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="user[about]"' in body
    assert b"hello" in body


def test_submit_accepts_followed_redirect_when_final_url_is_edit_page():
    calls = []
    from habr_career_mcp.client import HabrClient, Response
    client = HabrClient(cookie="")
    client._csrf = "csrf"
    def fake_request(path, method="GET", body=None, extra_headers=None):
        calls.append((path, method))
        return Response(200, "https://career.habr.com/profile/personal/edit", "saved")
    client._request = fake_request
    response = client.submit(
        "https://career.habr.com/profile/personal",
        "PATCH",
        [("_method", "patch"), ("user[about]", "hello")],
        multipart=True,
    )
    assert response.status == 200
    assert response.url.endswith("/profile/personal/edit")
