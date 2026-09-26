import pytest

from habr_career_mcp.service import ProfileService


PAGE_400 = """
<meta name="csrf-token" content="x">
<form action="/profile/specialization" method="post">
<input type="hidden" name="_method" value="patch">
<input name="user[salary]" value="400000">
<input name="user[title]" value="Backend Developer">
</form>
"""

PAGE_500 = PAGE_400.replace('value="400000"', 'value="500000"')


class FakeClient:
    def __init__(self):
        self.page = PAGE_400
        self.submits = []

    def get_text(self, path):
        return self.page

    def submit(self, action, method, fields):
        self.submits.append((action, method, list(fields)))
        salary = dict(fields).get("user[salary]")
        if salary:
            self.page = PAGE_400.replace('value="400000"', f'value="{salary}"')
        return type("R", (), {"status": 200, "url": action, "text": "успешно"})()


def test_preview_does_not_write_and_contains_diff():
    client = FakeClient()
    service = ProfileService(client)
    preview = service.preview_update("/profile/specialization", {"user[salary]": "500000"})
    assert client.submits == []
    assert preview["changes"]["user[salary]"] == {"old": ["400000"], "new": ["500000"]}
    assert preview["preview_id"]


def test_apply_uses_preview_and_verifies_saved_value():
    client = FakeClient()
    service = ProfileService(client)
    preview = service.preview_update("/profile/specialization", {"user[salary]": "500000"})
    result = service.apply_update(preview["preview_id"])
    assert result["status"] == "saved"
    assert result["verified"]["user[salary]"] == ["500000"]
    assert len(client.submits) == 1


def test_apply_rejects_stale_preview():
    client = FakeClient()
    service = ProfileService(client)
    preview = service.preview_update("/profile/specialization", {"user[salary]": "500000"})
    client.page = PAGE_500
    with pytest.raises(RuntimeError, match="stale preview"):
        service.apply_update(preview["preview_id"])
    assert client.submits == []


def test_preview_supports_repeated_field_replacement():
    client = FakeClient()
    service = ProfileService(client)
    preview = service.preview_update("/profile/specialization", {"user[tag_ids][]": ["1", "2"]})
    assert preview["changes"]["user[tag_ids][]"]["new"] == ["1", "2"]
