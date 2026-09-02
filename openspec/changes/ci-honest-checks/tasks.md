# Tasks — CI runs the checks it claims to (issue #9)
- [ ] 0.1 BLOCKED until an Actions billing budget exists — without minutes every run fails in 4s
      with no job, which is indistinguishable from a test failure
- [ ] 1.1 Python job: `uv sync --frozen` + `make check`
- [ ] 1.2 [nachtkarte PR] Web job: `npm ci`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`
- [ ] 1.3 [nachtkarte PR] Add an explicit `typecheck` script to `package.json`
- [ ] 2.1 [nachtkarte PR] Remove `typescript.ignoreBuildErrors` and the unsupported `eslint` key from next.config.ts
- [ ] 2.2 Fix the failures this surfaces (17 ESLint errors, tsc failures) — may warrant its own PR
- [ ] 3.1 After each job has succeeded on its default branch, mark `pipeline` and `web` as required
      status checks in their respective repositories where the GitHub plan permits it
