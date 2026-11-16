# STATE - Fallout 4 Forge

- Version: 0.1.1 (released; 0.1.0 published first, 0.1.1 fixes the test walker in extracted copies).
- Phase: M0-M9 done; M10 (CI, publish, release, hand-off, close) in progress.

## NEXT ACTION

**T43** - publish: `gh repo create SenjuWoo/Fallout4-Forge --public --source . --remote origin --push`, turn on
Dependabot alerts and secret scanning, wait for CI on the pushed SHA, query the alerts. Then T44 (release
v0.1.0 from the green SHA, verify the asset), T45 hand-off note, T46 close.

Start of every build session: read PLAN.md, this file and LOCAL.md; run `f4forge game` (runtime must read 1.11.240.0).

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
- 2026-11-15 M10 so far: CI/release/Dependabot workflows, bundle hand-off doc and test, local gate.

## Evidence (details per task in PLAN.md)

- Tests: 85 offline tests green (synthetic fixtures only); `f4forge selftest` exit 0; `f4forge doctor` exit 0 with
  all five sections ok on this PC.
- Installed truth: runtime 1.11.240.0, F4SE 0.7.9 matching, Address Library present, Creation Kit 1.11.246.0.
- Archives: 643/643 parse; Materials.ba2 and TexturesPatch.ba2 repacked identically, Archive2 agrees; 26081
  binary materials round-trip byte for byte.
- Records: worker find over 552 plugins in 3 s; 467355 EditorIDs indexed; worker-made plugins read back by the
  Python walker; Spriggit round trips record-equal.
- Papyrus: official compiler and Caprica both compile and both report planted errors as structured diagnostics.
- End-to-end: workspace project "Forge Smoke Test" built, checked (static and compile PASS), packaged and
  validated; deploy dry run clean. Load and gameplay NOT RUN.

## Gaps and open items

- In-game load of forge-written DX10 archives and of the smoke-test mod: NOT RUN (needs a game session).
- Creation Kit precombine/previs/facegen runs and CKPE deployment: dry runs only (NOT RUN by design).
- Animation (HKX) and interface (SWF): knowledge-only in 0.1 (D15).
- Compiling against a full decompiled import set (no-Creation-Kit tier) not run; a 50-script decompile sample matched.
- Bundle: its `--roots` flag does not reach self-registration (field report filed); registry and
  `ai-tooling-stack` rows wait for the bundle owner (docs/BUNDLE-ROW.md).
- Pattern launcher exit-code defect reported to Cyberpunk Forge (field report).

## Log

- 2026-11-15 plan written; Creation Kit installed by the owner; plan revised for the Creation Kit tier.
- 2026-11-15 M0-M9 built and committed; owner asked for the whole plan in one run (DECISIONS B9).
