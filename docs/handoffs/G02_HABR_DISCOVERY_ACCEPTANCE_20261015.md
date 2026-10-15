# G02 — Habr Career structured discovery and history acceptance

Date: 2026-10-15 (Europe/Moscow)
Host: Windows, Source checkout C:\Users\FoxOS_User\habr-career-mcp
Runtime: CodexifyGo Windows Service + stdio habr_career MCP, Python 3.12.10
Status: PASS — G02 structured read-only discovery and exact-ID response history.

## Git and deployment

- Pre-existing Windows checkout changes preserved in commit 46c6bff.
- Structured search PR #2 integrated to master in merge commit e94885b.
- Complete active/deleted response history reader added in da1353b.
- Commits pushed to origin/master; clean working tree verified.
- CodexifyGo Windows service restarted after each feature deployment.
- Upstream habr_career MCP exposes seven tools, including:
  - habr_search_vacancies(query, page, limit, previous_page_fingerprint?)
  - habr_get_response_history(include_deleted=true)

## Live MCP acceptance evidence

| Verification | Observed |
| --- | --- |
| Authenticated Habr account | true |
| Fullstack first page | 25 structured records |
| Untruncated HTML first page | 450,401 characters |
| Fullstack first page navigation | next_page=2; search_complete=false |
| Fullstack second page | 1 structured record |
| Unique Fullstack IDs | 26 total; 0 overlap |
| Fullstack second page navigation | next_page=null; search_complete=true |
| Titles and canonical URLs | 26/26 present |
| Full active response history | 2 records |
| Full deleted response history | 0 records |
| History pages | 1 active page; 1 deleted page |
| Exact-ID history uniqueness | 2/2 |
| history_complete | true |

These are live snapshots, not a guarantee that future job inventory will remain unchanged.
No applicant personal data or session material is stored in this report.

## Tests and acceptance scope

- Full repository tests: 42 passed.
- Offline server check: PASS.
- Python compileall: PASS.
- GitHub Actions on structured-search PR #2: 34 tests passed before merge.
- Search fixtures cover >100 KB HTML, paginated listings, redirects, repeated
  page fingerprints, unrelated cards, unknown pagination, HTTP failures,
  missing salary and duplicate vacancy IDs.
- History fixtures cover active/deleted buckets, duplicate bucket identities,
  pagination, missing pages, unknown counts, login redirect and HTTP failures.
- The new tools are read-only; application and profile mutation paths unchanged.

## Integration contract for G03–G06 in work-search

1. Traverse pages using next_page and pass the previous page_fingerprint.
   A partial source result or failure is never an exhaustive search claim.
2. Distinguish listing discovery, full-description reading, screening and
   already_applied states. Do not dedupe away an unscreened raw listing.
3. Use habr_get_response_history(include_deleted=true) before deduplication.
   Any partial history or thrown error must stop claims of full history coverage.
4. Combine HH active+deleted, Habr active+deleted, and durable manual/approved
   application journal without collapsing distinct jobs at one employer.
5. Treat Habr predicted salary as unknown unless the employer disclosed it.
6. Keep cookies, raw applicant pages, resume data and secret state out of Git.
7. Leave Vacancy Hourly Watch disabled; send no applications.

## Remaining

- G03: durable multi-stage triage backlog; idempotent queue resume;
  metrics and host-owned append-only run events in work-search.
- G04: Geekjob, Getmatch and employer career-site source adapters.
- G05: reconcile disabled task state with monitoring/setup.json and docs.
- G06: fixture-backed source recall and cross-source end-to-end acceptance.

The conversation remains bound to habr-career-mcp. Use CodexifyGo's project
switch UI to select work-search / Source checkout before modifying that repo;
call get_agent_brief and inspect git status on that workspace.
