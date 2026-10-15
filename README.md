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

Recommended: use the same browser-session flow as hh-mcp-server:

    .venv/bin/python server.py --login

A visible Chromium window opens. Log in only on career.habr.com; after protected profile access is verified, Playwright state is stored with private permissions under ~/.habr-career-mcp/profile/state.json. The HTTP client automatically reuses Career Habr cookies from that state.

Manual HABR_COOKIE/.env authentication remains available as a fallback.


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
- habr_search_vacancies: read a full untruncated listings page, returning canonical vacancy IDs, title, employer, declared salary, publish timestamp, source page, next page, and explicit completeness signals. Call once per page; do not treat `pagination_unverified` as exhaustive search. This is read-only.
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


### Habr read-only vacancy discovery

\`habr_search_vacancies(query="Fullstack", page=1, limit=50)\` parses the **complete**
authenticated HTTP response on the server before serializing a compact listing. 
It does not create or send job applications, edit a profile or change existing
\`habr_get\` behavior.

Check \`next_page\` and \`search_complete\` after each call; follow the returned
\`next_page\` rather than assuming a fixed page count. For the next page pass the
previous result's \`page_fingerprint\` as \`previous_page_fingerprint\`.
A repeated page, unexpected redirect or changed query raises an error rather than
claiming complete search coverage.

\`pagination_verified=false\`, \`search_complete=false\`, \`limit_truncated=true\`
or a nonterminal \`stop_reason\` must be recorded as partial coverage in the caller.
\`salary_raw=null\` means the employer did **not** disclose compensation; Habr's
predicted salary is intentionally excluded. Persist source ID, canonical URL
and publish timestamp, then separately verify the full vacancy description
before screening. A result appearing in discovery is not a completed screening.

## Development checks

    . .venv/bin/activate
    pytest -q
    python3 server.py --check
    python3 -m compileall -q src server.py

## Why not the official Career Habr OAuth API?

The public API is useful for reading data, but the profile edit workflow is not exposed as a documented write API. The browser edits Rails forms with CSRF. This project intentionally mirrors that observed mechanism while adding preview, stale-state detection and post-write verification.
