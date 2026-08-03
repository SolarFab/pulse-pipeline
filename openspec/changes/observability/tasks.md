# Tasks — Observability (blocked on LANGFUSE_* keys from the user)
- [x] 1.1 [web] Langfuse TS SDK in chat route: trace per turn, guarded no-op (VERIFIED in prod: concierge-turn trace with userId; two real bugs fixed: instrumentation.ts must live in src/, and prod bundles need a globalThis singleton processor)
- [ ] 1.1b [web] AI SDK telemetry generation/tool child-spans missing in prod bundle — investigate OTEL api duplication
- [x] 1.2 [web] Vercel env vars set + verified (gotcha documented: values pasted with quotes break auth silently)
- [x] 2.1 [pipeline] Python SDK generations in stage-2 harness (model, tokens, measured cost; per-case spans)
- [ ] 2.2 [capstone] (tracked in discovery-agent 3.4) scout callback — same project, tag=scout
- [ ] 3.1 Docs: dashboard conventions + how to read a trace (showcase screenshot)
