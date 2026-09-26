import hashlib
import html as html_lib
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

FieldPairs = List[Tuple[str, str]]


@dataclass
class ParsedForm:
    action: str
    method: str
    fields: FieldPairs
    schema: List[dict]
    ssr: Optional[dict]


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: List[dict] = []
        self._textarea: Optional[dict] = None
        self._select: Optional[dict] = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "form":
            self.forms.append({
                "action": a.get("action", ""),
                "method": a.get("method", "get").upper(),
                "fields": [],
            })
            return
        if not self.forms:
            return
        if tag in ("input", "textarea", "select") and a.get("name"):
            item = {"name": a["name"], "tag": tag}
            if a.get("type"):
                item["type"] = a["type"]
            if tag == "input":
                input_type = a.get("type", "text")
                if input_type not in ("checkbox", "radio") or "checked" in a:
                    item["value"] = a.get("value", "")
            self.forms[-1]["fields"].append(item)
            if tag == "textarea":
                self._textarea = item
            elif tag == "select":
                self._select = item
        elif tag == "option" and self._select is not None:
            self._select.setdefault("options", []).append(a.get("value", ""))
            if "selected" in a:
                self._select["value"] = a.get("value", "")

    def handle_data(self, data):
        if self._textarea is not None:
            self._textarea["value"] = self._textarea.get("value", "") + data

    def handle_endtag(self, tag):
        if tag == "textarea":
            self._textarea = None
        elif tag == "select":
            self._select = None


def extract_ssr(page: str) -> Optional[dict]:
    match = re.search(r"<script[^>]*data-ssr-state[^>]*>(.*?)</script>", page, re.S | re.I)
    if not match:
        return None
    return json.loads(html_lib.unescape(match.group(1)))


def vue_fields(ssr: Optional[dict]) -> FieldPairs:
    if not ssr:
        return []
    out: FieldPairs = []
    for selected_key, field_key in (
        ("selectedSkills", "skillsFieldName"),
        ("selectedCategories", "categoryFieldName"),
    ):
        name = ssr.get(field_key)
        if not name:
            continue
        for value in ssr.get(selected_key) or []:
            if isinstance(value, dict):
                value = value.get("value")
            if value is not None:
                out.append((name, str(value)))

    for lang in ssr.get("selectedLanguages") or []:
        if "languageId" in lang:
            out.append(("user[foreign_languages][][language_id]", str(lang["languageId"])))
        if "gradeId" in lang:
            out.append(("user[foreign_languages][][grade_id]", str(lang["gradeId"])))

    prefix = ssr.get("fieldName")
    if prefix:
        for key, part in (("startDate", "start_date"), ("endDate", "end_date")):
            value = ssr.get(key)
            if not value:
                continue
            year, month, _day = value.split("-")
            out.extend([
                (f"{prefix}[{part}(1i)]", year),
                (f"{prefix}[{part}(2i)]", str(int(month))),
                (f"{prefix}[{part}(3i)]", "1"),
            ])
    return out


def parse_page(page: str) -> ParsedForm:
    parser = _FormParser()
    parser.feed(page)
    ssr = extract_ssr(page)
    for form in parser.forms:
        if form["action"].endswith("sign_out"):
            continue
        if not form["fields"]:
            continue
        fields: FieldPairs = []
        for field in form["fields"]:
            if field["name"] == "authenticity_token":
                continue
            if "value" in field:
                fields.append((field["name"], str(field["value"]).strip()))
        fields.extend(vue_fields(ssr))
        method = form["method"]
        for key, value in fields:
            if key == "_method":
                method = value.upper()
                break
        return ParsedForm(
            action=form["action"],
            method=method,
            fields=fields,
            schema=form["fields"],
            ssr=ssr,
        )
    raise ValueError("no editable form found; authentication may be required")


def merge_fields(base: Sequence[Tuple[str, str]], changes: Dict[str, object]) -> FieldPairs:
    override = {key: str(value) for key, value in changes.items()}
    merged: FieldPairs = []
    replaced = set()
    for key, value in base:
        if key not in override:
            merged.append((key, value))
        elif key not in replaced:
            merged.append((key, override[key]))
            replaced.add(key)
    for key, value in override.items():
        if key not in replaced:
            merged.append((key, value))
    return merged


def form_state_hash(fields: Iterable[Tuple[str, str]]) -> str:
    payload = json.dumps(list(fields), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def scalar_values(fields: Sequence[Tuple[str, str]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for key, value in fields:
        result[key] = value
    return result
