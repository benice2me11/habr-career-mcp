# Habr Career MCP Design

## Goal

Provide a small independent MCP server for safely reading and editing the authenticated user's Career Habr profile without coupling it to hh-mcp-server or work-search.

## Authentication

Use the user's existing career.habr.com browser session cookie supplied through HABR_COOKIE or a local .env file. Secrets are never committed. CSRF tokens are fetched from the authenticated site and sent on writes.

## Architecture

The MCP has four layers:

1. client.py owns HTTP, session cookies, CSRF retrieval, GETs and form submission.
2. forms.py parses the site's actual Rails forms and Vue SSR state instead of hardcoding field schemas.
3. service.py implements read, preview and apply semantics. Preview never writes; apply performs read-modify-write and then re-reads the page to verify requested fields.
4. server.py exposes a narrow MCP surface.

The project intentionally discovers form actions, methods and field names from Career Habr itself. It does not guess endpoints or selectors beyond stable entry-page paths supplied by the caller.

## Safety model

- Writes are impossible through preview tools.
- Apply requires the exact preview_id returned by a prior preview in the same process.
- A preview includes requested old/new values and a hash of the source form state.
- Apply re-fetches the form and rejects the write if the source state changed since preview.
- Unchanged form values are resent so Rails does not blank omitted fields.
- Repeated array fields from Vue state are preserved.
- After a successful request, the MCP re-fetches the page and verifies every requested scalar field.
- .env, cookies and local state are gitignored.

## MCP tools

- habr_whoami()
- habr_form(path)
- habr_preview_update(path, changes)
- habr_apply_update(preview_id)
- habr_get(path, raw=False)

The generic form-driven API is deliberate: Career Habr's profile pages remain the schema source, so the MCP is less brittle than a large collection of duplicated typed field definitions.

## Initial supported entry pages

The implementation is expected to work with the site's current profile forms, including:

- /profile/personal/edit
- /profile/specialization
- experience and education create/edit pages discovered from profile HTML

No destructive delete operation is included in the MVP.

## Testing

Offline tests cover form parsing, Vue field extraction, read-modify-write merging, preview hashing, stale-preview rejection and post-write verification. A live --check-live command validates authentication and CSRF without editing data.
