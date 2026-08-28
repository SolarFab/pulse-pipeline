# Tasks — Test isolation (issue #10)
- [ ] 1.1 Add `pytest-socket` as a dev dependency via `uv add --dev`
- [ ] 1.2 Enable `--disable-socket` by default in `pyproject.toml`
- [ ] 1.3 `tests/conftest.py`: shared fixture stubbing the geocoder + Supabase client
- [ ] 2.1 Run the suite, list every test that now fails on a socket, fix each individually
- [ ] 2.2 Confirm the FEAT-9 case: `test_scrape_failure_reporting.py` passes with its local
      autouse fixture REMOVED, because the global fence covers it
- [ ] 3.1 CI passes a test-scoped environment, not the production one
- [ ] 4.1 Web: verify Vitest does not reach Supabase or OpenRouter (routing.test.ts already stubs
      fetch — check the other two files)
