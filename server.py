#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from habr_career_mcp.client import HabrClient
from habr_career_mcp.service import ProfileService


TOOLS = [
    {
        "name": "habr_whoami",
        "description": "Check the authenticated Career Habr account without modifying anything.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "habr_get",
        "description": "GET a Career Habr path. HTML scripts/styles are stripped unless raw=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "raw": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 20000, "minimum": 1, "maximum": 100000},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "habr_form",
        "description": "Read the editable form schema, current values and Vue SSR state for a Career Habr page.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "habr_preview_update",
        "description": "Preview profile changes without writing. Returns a one-time preview_id required by apply.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "changes": {
                    "type": "object",
                    "description": "Form field names to new scalar or array values.",
                    "additionalProperties": True,
                },
            },
            "required": ["path", "changes"],
            "additionalProperties": False,
        },
    },
    {
        "name": "habr_apply_update",
        "description": "Apply an exact prior preview if the source form is unchanged, then verify the saved values.",
        "inputSchema": {
            "type": "object",
            "properties": {"preview_id": {"type": "string"}},
            "required": ["preview_id"],
            "additionalProperties": False,
        },
    },
]


class App:
    def __init__(self, client=None):
        self.client = client or HabrClient()
        self.service = ProfileService(self.client)

    def whoami(self) -> Dict[str, Any]:
        page = self.client.get_text("/")
        login_match = re.search(r'class=["\'][^"\']*menu-head[^"\']*["\'][^>]*href=["\']/([\w.-]+)', page, re.I)
        if not login_match:
            return {"authenticated": False, "login": None}
        name_match = re.search(r'class=["\'][^"\']*menu-head__name[^"\']*["\'][^>]*>([^<]+)', page, re.I)
        return {
            "authenticated": True,
            "login": login_match.group(1),
            "name": name_match.group(1).strip() if name_match else None,
        }

    def call(self, name: str, args: Dict[str, Any]) -> Any:
        if name == "habr_whoami":
            return self.whoami()
        if name == "habr_get":
            path = args["path"]
            raw = bool(args.get("raw", False))
            limit = int(args.get("limit", 20000))
            response = self.client.get(path)
            body = response.text
            if not raw and body.lstrip().startswith("<"):
                body = re.sub(r"<(script|style|svg)\b.*?</\1>", "", body, flags=re.S | re.I)
            if len(body) > limit:
                body = body[:limit] + f"\n...[truncated, {len(response.text)} chars total]"
            return {"status": response.status, "url": response.url, "body": body}
        if name == "habr_form":
            return self.service.form(args["path"])
        if name == "habr_preview_update":
            return self.service.preview_update(args["path"], args["changes"])
        if name == "habr_apply_update":
            return self.service.apply_update(args["preview_id"])
        raise KeyError(f"unknown tool: {name}")


def _text_result(value: Any) -> Dict[str, Any]:
    body = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return {"content": [{"type": "text", "text": body}]}


def handle_message(app: App, message: Dict[str, Any]) -> Dict[str, Any]:
    method = message.get("method")
    request_id = message.get("id")

    if method == "initialize":
        requested = (message.get("params") or {}).get("protocolVersion")
        protocol = requested or "2025-06-18"
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "habr-career-mcp", "version": "0.1.0"},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            result = app.call(params.get("name", ""), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": request_id, "result": _text_result(result)}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                    "isError": True,
                },
            }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def serve() -> None:
    app = App()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
            print(json.dumps(response, ensure_ascii=False), flush=True)
            continue
        if "id" not in message:
            continue
        response = handle_message(app, message)
        print(json.dumps(response, ensure_ascii=False), flush=True)


def check_offline() -> int:
    from habr_career_mcp.forms import merge_fields, parse_page

    page = (
        '<form action="/profile/specialization" method="post">'
        '<input type="hidden" name="_method" value="patch">'
        '<input name="user[salary]" value="400000">'
        '</form>'
    )
    parsed = parse_page(page)
    assert parsed.action == "/profile/specialization"
    assert parsed.method == "PATCH"
    assert merge_fields(parsed.fields, {"user[salary]": "500000"})[-1] == ("user[salary]", "500000")
    print("offline check: OK")
    return 0


def check_live() -> int:
    app = App()
    who = app.whoami()
    print(json.dumps(who, ensure_ascii=False))
    if not who["authenticated"]:
        print("live check: not authenticated; set HABR_COOKIE or create .env", file=sys.stderr)
        return 2
    token = app.client.csrf()
    print(f"csrf: OK ({len(token)} chars)")
    print("live check: OK (read-only, no profile changes)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="run an offline parser smoke test")
    parser.add_argument("--check-live", action="store_true", help="check Career Habr auth and CSRF without writing")
    args = parser.parse_args()
    if args.check:
        return check_offline()
    if args.check_live:
        return check_live()
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
