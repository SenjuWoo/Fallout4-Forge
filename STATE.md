# STATE - Fallout 4 Forge

- Version: 0.1.1 (released). Public repository https://github.com/SenjuWoo/Fallout4-Forge (MIT).
- Releases: v0.1.0 (commit 8d9bbfa, asset sha256 73234a3c...) and v0.1.1 (commit 8454a6d, asset
  Fallout4-Forge-0.1.1-source.zip sha256 39b31e5264c0a0a0cb98860b34b297e665ca6bd3d7bc58566d82e6fc4a3a3994).
- Phase: PLAN.md complete (T01-T46). Installed and wired on this PC; `f4forge doctor` exit 0.

## NEXT ACTION

None in the plan. Open items below are for later versions or for other owners. A new session starts with
`f4forge doctor`, `f4forge game` (runtime must read 1.11.240.0) and this file.

## Done

- 2026-11-15 Planning (PLAN.md, LOCAL.md, WORKSPACE_OWNERSHIP.md).
- 2026-11-15 M0-M1: CLI contract, game discovery, doctor, knowledge, routing.
- 2026-11-15 M2: tool lock and sync (35 entries, SHA-256 pins, receipt), workspace seeded.
- 2026-11-15 M3: BA2 read/write (vanilla hash and chunk rules, Archive2 cross-check), plugin walker, light rule,
  load order, .NET records worker (Mutagen 0.54.4), Spriggit YAML tree.
- 2026-11-15 M4: Papyrus source cache, PEX reader, official compiler and Caprica behind one diagnostics format.
- 2026-11-15 M5: textures, BGSM/BGEM byte-exact, NIF + Blender/PyNifly, FUZ/XWM/LIP voice.
- 2026-11-15 M6: MCM, RobCo Patcher, Base Object Swapper, LooksMenu/BodySlide/INI validators, native F4SE
  (CommonLibF4 build), logs, Creation Kit wrappers.
- 2026-11-15 M7: projects (12 kinds), build, check with evidence tiers, deterministic package (+BA2, FOMOD),
  deploy/undeploy, bump, index, conflicts, Nexus lookups and page kit.
- 2026-11-15 M8: 28 knowledge topics with fact tags, skill, selftest, README, AGENTS, CHANGELOG, hygiene test.
- 2026-11-15 M9: installer/uninstaller, companion manifest, machine wiring, live install, end-to-end smoke test.
- 2026-11-15 M10: CI (11 jobs green), release workflow, Dependabot, publish, releases v0.1.0 and v0.1.1, hand-off.

## Evidence (details per task in PLAN.md)

| Tier | Result |
|---|---|
| Offline tests | 87 tests, green locally and in CI on ubuntu + windows for Python 3.10, 3.13, 3.14 |
| CI on 8454a6d | 11/11 check runs success (tests x6, templates, worker, papyrus, native, install) |
| Installed truth | runtime 1.11.240.0, F4SE 0.7.9 matching, Address Library present, Creation Kit 1.11.246.0 |
| Archives | 643/643 parse; Materials and TexturesPatch repacks identical; Archive2 agrees |
| Materials | 26081 binary materials byte-identical; 46 JSON-text read |
| Records | worker find over 552 plugins in 3 s; 467355 EditorIDs indexed; Spriggit round trips record-equal |
| Papyrus | official compiler and Caprica compile; planted errors give one structured diagnostic each |
| Native | CommonLibF4 template builds locally and in CI; exports F4SEPlugin_Load/Preload/Version |
| End-to-end | "Forge Smoke Test" in the workspace: static PASS, compile PASS, package and validate PASS |
| Release | v0.1.1 asset downloaded, SHA-256 matched, extracted, installed with a temp home, launcher 0.1.1, suite OK |
| Alerts | Dependabot 0 open, secret scanning 0 open, code scanning (CodeQL default setup) 0 open (2026-11-25) |
| Load / gameplay | NOT RUN (no game session in this build) |

## Gaps and open items

- In-game load of forge-written DX10 archives and of the smoke-test mod: NOT RUN.
- Creation Kit precombine/previs/facegen runs and CKPE deployment: dry runs only, NOT RUN by design.
- Animation (HKX) and interface (SWF): knowledge-only in 0.1 (D15).
- No-Creation-Kit tier: a 50-script Champollion sample matched the official sources; compiling against a full
  decompiled import set is not run.
- Bundle hand-off open for the bundle owner: registry row and `ai-tooling-stack` row in `docs/BUNDLE-ROW.md`;
  the bundle's `--roots` flag does not reach self-registration (field report filed in the bundle).
- Cyberpunk Forge launcher loses exit codes inside an `if` block (field report filed in that forge).

## Log

- 2026-11-15 plan written; Creation Kit installed by the owner; plan revised for the Creation Kit tier.
- 2026-11-15 M0-M9 built and committed; owner asked for the whole plan in one run (DECISIONS B9).
- 2026-11-15 published; v0.1.0 released, v0.1.1 released and verified (DECISIONS B19).
- 2026-11-25 presentation pass (docs only, no version change): README rewritten, `docs/icon.svg`, cover and
  terminal shots in `docs/presentation/` from real runs (game, doctor, plan, records find, new -> records new
  -> build -> check --compile -> package -> deploy dry run, all exit 0). Suite 87 tests green.
