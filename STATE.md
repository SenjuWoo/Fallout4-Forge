# STATE - Fallout 4 Forge

- Version: 0.1.0 (in development, not released). Local git repository on `main`, no remote.
- Phase: building. M0 (T01-T03) and M1 (T04-T07) done; next milestone M2 (T08-T10).

## NEXT ACTION

**T08** - `tools.lock.json` + `tools.py` ported from `<PATTERN_LOCK>` (kinds, fields, `tools status`,
`tools sync --approve`, SHA-256 before extraction, receipt, generated `TOOLS.md`, local HTTP
fixture tests). Then T09 (pin the real tools) and T10 (seed the workspace), finishing M2.

Start of every build session: read PLAN.md, this file and LOCAL.md; run `f4forge game` once
(assumption A15: runtime must still read 1.11.240.0).

Builder prompt (same text every session, Opus High or Medium per PLAN.md):

> Build Fallout 4 Forge from PLAN.md. Read PLAN.md, STATE.md and LOCAL.md, continue at NEXT
> ACTION, finish the current milestone under the plan's rules, update STATE.md, commit, stop.

## Done

- 2026-11-15 Planning: orientation, research, PLAN.md, LOCAL.md, WORKSPACE_OWNERSHIP.md.
- 2026-11-15 M0: repository bootstrap, package skeleton (`cli`, `util`, `home`, launcher, test
  runner), mirror, line-ending and awkward-path launcher tests.
- 2026-11-15 M1: `game` discovery (pure-Python PE version reader, Steam/registry/GOG,
  F4SE, Address Library, official masters, Creation Club, Creation Kit tools and sources,
  frameworks, My Games, mod managers, archive and plugin header censuses), `doctor` in five
  sections, knowledge data (17 facts with tiers, 21 frameworks, 24 routes, 28 topic names),
  `knowledge`, `facts`, `plan`, `capabilities`, `config`.

## Evidence

- `python tests/run_tests.py`: 36 tests OK (synthetic fixtures only).
- On this PC `f4forge game`: runtime 1.11.240.0 (Steam build 24564252), F4SE 0.7.9 matching,
  Address Library present, Creation Kit 1.11.246.0 with its compiler, Archive2, LipGenerator and
  xwmaencode; `--archives`: 643 archives, 0 header errors, version/type counts equal LOCAL.md.
- `f4forge doctor`: exit 0 (toolchain, game, payload ok; tools and worker degraded until M2/M3);
  with `FALLOUT4_ROOT` at an empty folder: game fail, exit 2.
- Per-task evidence is in PLAN.md; deviations are B1-B8 in DECISIONS.md.

## Gaps and open items

- `tools` and `worker` doctor sections are `degraded` by design until T08/T09 and T15.
- No knowledge topic text yet (28 names listed; T33 writes them).
- `load_order.official_masters` is `unverified` until T14.
- Assumptions A2-A19 unchecked; A1 and A15 hold (runtime 1.11.240.0 read this session).
- Field report filed for the pattern's launcher (exit code lost inside an `if` block); see
  DECISIONS B1. The bundle's registry rows remain a hand-off (T45).

## Log

- 2026-11-15 plan written; Creation Kit installed by the owner; plan revised for the Creation Kit tier.
- 2026-11-15 M0 + M1 built, tests green, committed.
