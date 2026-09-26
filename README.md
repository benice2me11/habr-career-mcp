# habr-career-mcp

Independent, safety-first MCP server for reading and editing your own profile on Career Habr.

It does not use guessed write endpoints. It reads the real Career Habr Rails form, preserves its current fields, submits the form action/method with CSRF protection, and verifies the saved value by reading the page again.

## Safety model

Profile edits are two-step:

1. habr_preview_update reads the current form and returns old/new values plus a preview_id. It does not write.
2. habr_apply_update accepts only that preview_id. Before writing it re-reads the form and rejects stale previews. After writing it re-reads again and verifies every requested field.

This protects against accidental blind writes and against Rails blanking fields omitted from a whole-form submission. Repeated values such as skills and languages are preserved.

There are no delete tools in the MVP.

## Requirements

Python 3.9 or newer. Runtime uses only the standard library.

For tests:

    python3 -m venv .venv
    . .venv/bin/activate
    python -m pip install pytest

## Authentication

Copy the example:

    cp .env.example .env

In a browser already logged in to career.habr.com, open DevTools -> Application/Storage -> Cookies and copy the Career Habr session cookies. Put the full Cookie header value into HABR_COOKIE.

The .env file is gitignored.

Read-only verification:

    python3 server.py --check-live

Expected result contains authenticated=true and csrf=OK. This command never edits the profile.

## MCP configuration

Example stdio configuration:

    {
      "mcpServers": {
        "habr-career": {
          "command": "python3",
          "args": ["/Users/whtvr/prjctx/habr-career-mcp/server.py"]
        }
      }
    }

The server also reads HABR_COOKIE directly from the MCP process environment if you prefer not to use .env.

## Tools

- habr_whoami: check the logged-in Career Habr account.
- habr_get: read a Career Habr page.
- habr_form: inspect the actual editable form and current values.
- habr_preview_update: prepare a diff; performs no write.
- habr_apply_update: apply exactly one prior preview and verify the result.

Useful current entry pages discovered during research:

- /profile/personal/edit
- /profile/specialization
- experience/education edit pages linked from the authenticated profile

Use habr_form before changing a page. The page itself is the schema.

## Example safe flow

Call:

    habr_form("/profile/specialization")

Then preview only the intended field:

    habr_preview_update(
      "/profile/specialization",
      {"user[salary]": "500000"}
    )

Inspect the returned diff. Only then call:

    habr_apply_update("<preview_id>")

If the page changed between preview and apply, apply refuses to write and requires a new preview.

## Development checks

    . .venv/bin/activate
    pytest -q
    python3 server.py --check
    python3 -m compileall -q src server.py

## Why not the official Career Habr OAuth API?

The public API is useful for reading data, but the profile edit workflow is not exposed as a documented write API. The browser edits Rails forms with CSRF. This project intentionally mirrors that observed mechanism while adding preview, stale-state detection and post-write verification.
