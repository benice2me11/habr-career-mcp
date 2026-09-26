import json

from habr_career_mcp.forms import parse_page, merge_fields, form_state_hash


def test_parse_form_scalars_arrays_textarea_select_and_vue():
    ssr = {
        "selectedSkills": [{"value": 10}, {"value": 20}],
        "skillsFieldName": "user[skills][]",
        "selectedLanguages": [{"languageId": 1, "gradeId": 4}],
    }
    page = f"""
    <html><body>
      <form action="/profile/specialization" method="post">
        <input type="hidden" name="_method" value="patch">
        <input name="user[salary]" value="400000">
        <input type="hidden" name="user[remote]" value="0">
        <input type="checkbox" name="user[remote]" value="1" checked>
        <textarea name="user[about]">Backend developer</textarea>
        <select name="user[qid]">
          <option value="3">Junior</option>
          <option value="4" selected>Middle</option>
        </select>
      </form>
      <script data-ssr-state>{json.dumps(ssr)}</script>
    </body></html>
    """
    parsed = parse_page(page)
    assert parsed.action == "/profile/specialization"
    assert parsed.method == "PATCH"
    assert ("user[salary]", "400000") in parsed.fields
    assert ("user[remote]", "0") in parsed.fields
    assert ("user[remote]", "1") in parsed.fields
    assert ("user[about]", "Backend developer") in parsed.fields
    assert ("user[qid]", "4") in parsed.fields
    assert ("user[skills][]", "10") in parsed.fields
    assert ("user[skills][]", "20") in parsed.fields
    assert ("user[foreign_languages][][language_id]", "1") in parsed.fields
    assert ("user[foreign_languages][][grade_id]", "4") in parsed.fields


def test_merge_fields_replaces_only_requested_keys_and_preserves_duplicates():
    base = [
        ("user[salary]", "400000"),
        ("user[skills][]", "10"),
        ("user[skills][]", "20"),
    ]
    merged = merge_fields(base, {"user[salary]": "500000"})
    assert merged == [
        ("user[salary]", "500000"),
        ("user[skills][]", "10"),
        ("user[skills][]", "20"),
    ]


def test_form_state_hash_is_order_sensitive_for_repeated_fields_but_stable():
    fields = [("a", "1"), ("b[]", "x"), ("b[]", "y")]
    assert form_state_hash(fields) == form_state_hash(list(fields))
    assert form_state_hash(fields) != form_state_hash([("a", "1"), ("b[]", "y"), ("b[]", "x")])
