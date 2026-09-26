import re
import uuid
from dataclasses import dataclass
from typing import Dict, List

from .forms import form_state_hash, grouped_values, merge_fields, parse_page


@dataclass
class Preview:
    preview_id: str
    path: str
    changes: Dict[str, object]
    source_hash: str


def _as_list(value: object) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _validation_errors(body: str) -> List[str]:
    errors = re.findall(r"validation-error[^>]*>([^<]+)<", body, re.I)
    return list(dict.fromkeys(item.strip() for item in errors if item.strip()))


class ProfileService:
    def __init__(self, client):
        self.client = client
        self._previews: Dict[str, Preview] = {}

    def form(self, path: str) -> dict:
        parsed = parse_page(self.client.get_text(path))
        return {
            "path": path,
            "action": parsed.action,
            "method": parsed.method,
            "fields": grouped_values(parsed.fields),
            "schema": parsed.schema,
            "ssr": parsed.ssr,
            "state_hash": form_state_hash(parsed.fields),
        }

    def preview_update(self, path: str, changes: Dict[str, object]) -> dict:
        if not changes:
            raise ValueError("changes must not be empty")
        parsed = parse_page(self.client.get_text(path))
        before = grouped_values(parsed.fields)
        preview_id = uuid.uuid4().hex
        change_view = {}
        for key, value in changes.items():
            change_view[key] = {
                "old": before.get(key, []),
                "new": _as_list(value),
            }
        preview = Preview(
            preview_id=preview_id,
            path=path,
            changes=dict(changes),
            source_hash=form_state_hash(parsed.fields),
        )
        self._previews[preview_id] = preview
        return {
            "preview_id": preview_id,
            "path": path,
            "action": parsed.action,
            "method": parsed.method,
            "source_hash": preview.source_hash,
            "changes": change_view,
            "notice": "No write has occurred. Apply requires this preview_id and unchanged source state.",
        }

    def apply_update(self, preview_id: str) -> dict:
        preview = self._previews.get(preview_id)
        if preview is None:
            raise KeyError("unknown or expired preview_id")

        current = parse_page(self.client.get_text(preview.path))
        current_hash = form_state_hash(current.fields)
        if current_hash != preview.source_hash:
            raise RuntimeError("stale preview: source form changed; create a new preview before applying")

        fields = merge_fields(current.fields, preview.changes)
        response = self.client.submit(current.action, current.method, fields, multipart=preview.path.startswith("/profile/personal/"), referer=preview.path)
        errors = _validation_errors(response.text)
        if errors:
            raise RuntimeError("Career Habr validation failed: " + "; ".join(errors))
        # Career Habr AJAX forms can save successfully and then produce a 404 in
        # urllib's redirect handling. The authoritative success signal is the
        # protected edit form read-back below, not the transport's final status.
        verified_form = parse_page(self.client.get_text(preview.path))
        after = grouped_values(verified_form.fields)
        mismatches = {}
        verified = {}
        for key, value in preview.changes.items():
            expected = _as_list(value)
            actual = after.get(key, [])
            if actual != expected:
                mismatches[key] = {"expected": expected, "actual": actual}
            else:
                verified[key] = actual
        if mismatches:
            raise RuntimeError(f"write response returned but verification failed: {mismatches}")

        del self._previews[preview_id]
        return {
            "status": "saved",
            "path": preview.path,
            "http_status": response.status,
            "verified": verified,
        }
