# Habr Career MCP Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

Goal: Build an independent MCP server that safely previews and applies Career Habr profile edits using the site's real forms and browser session.

Architecture: HTTP/session logic, form parsing, safe preview/apply service, and MCP transport are separate modules. Writes use read-modify-write, stale-state detection, and post-write verification.

Tech Stack: Python 3.11+, httpx, mcp>=2, stdlib html.parser, pytest.

### Task 1: Project skeleton and parser
Files: pyproject.toml, .gitignore, src/habr_career_mcp/forms.py, tests/test_forms.py
- [ ] Add packaging/dependencies and secret ignores.
- [ ] Write failing parser tests for Rails scalar fields, duplicate array fields, textareas, selects and Vue SSR state.
- [ ] Implement parser and run pytest tests/test_forms.py -q.
- [ ] Commit parser foundation.

### Task 2: HTTP client
Files: src/habr_career_mcp/client.py, tests/test_client.py
- [ ] Test cookie normalization, CSRF extraction and URL-encoded repeated fields.
- [ ] Implement authenticated httpx.Client, CSRF cache and request helpers.
- [ ] Run focused tests.
- [ ] Commit client layer.

### Task 3: Safe preview/apply service
Files: src/habr_career_mcp/service.py, tests/test_service.py
- [ ] Test read-modify-write merge, preview diff, source hash, stale preview rejection and verification.
- [ ] Implement in-memory preview store and safe apply.
- [ ] Run focused tests.
- [ ] Commit service layer.

### Task 4: MCP server and CLI checks
Files: server.py, README.md, .env.example
- [ ] Expose whoami, get, form, preview_update, apply_update.
- [ ] Add --check offline test runner and --check-live auth/CSRF check.
- [ ] Document setup and safe edit workflow.
- [ ] Run full test suite and compile check.
- [ ] Commit MCP surface/docs.

### Task 5: Final verification
- [ ] Run pytest -q.
- [ ] Run python -m compileall -q src server.py.
- [ ] Confirm .env is ignored and no cookie-like secret is tracked.
- [ ] Review final diff/status.
