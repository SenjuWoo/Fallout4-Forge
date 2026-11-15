# Decisions

Settled during planning (PLAN.md, D1-D15). Not reopened by the build.

| # | Chosen | Rejected, and why |
|---|---|---|
| D1 | Lean forge on the Cyberpunk Forge pattern: `src/` package, data-driven knowledge, one test file, about 30 commands | Forking Skyrim Forge: most of it is Skyrim policy; porting costs more than building the Fallout 4 parts fresh |
| D2 | The checkout is the install: `.venv` in the checkout, launcher under the forge home | A second runtime copy under LOCALAPPDATA |
| D3 | One skill, `fallout4-forge`; specialist knowledge served by `f4forge knowledge <topic>` | A large skill pack loaded into every session |
| D4 | Records: Spriggit YAML tree as source of truth, a small Mutagen worker, a pure-Python header/index reader | xEdit scripting as the main route; a hand-written Python record writer |
| D5 | Two tiers chosen by what `game` finds: Creation Kit (official compiler, sources, Archive2, voice tools, wrapped CK runs) or not (native BA2, Champollion, Caprica; CI runs here) | Requiring the Creation Kit; dropping Caprica |
| D6 | One tools folder driven by `tools.lock.json` with hashes and a receipt; installed tools referenced, not copied; FO4Edit gets its own copy | Copying another tools folder; unpinned ad-hoc downloads |
| D7 | CommonLibF4 from `libxse/commonlibf4` pinned by commit, built with xmake | Older lineages no longer receiving runtime fixes |
| D8 | No MCP server in 0.1; CLI plus JSON | A second interface before the first is proven |
| D9 | Deployment is an explicit command, dry run by default | Automatic deploy into a mod-manager-controlled Data folder |
| D10 | Nexus-only tools are `manual` entries with detection | Scripting Nexus downloads |
| D11 | Names: `Fallout4-Forge`, `Fallout 4 Forge`, `f4forge`, `fallout4-forge`, home `Fallout4Forge` | Names that do not normalise to the repository name |
| D12 | Public MIT repository, source-zip release by `git archive` | A release zip bundling third-party binaries |
| D13 | The BA2 writer emits version 1 by default | Version 8 by default |
| D14 | Bundle wiring through `uabs-companion.json` plus one tool-root line; the registry row is handed to the bundle maintainer | Editing the bundle from this project |
| D15 | 0.1 ships knowledge-only routes for animation (HKX) and interface (SWF); voice and previs/precombine/facegen are real on the Creation Kit tier | Holding the release until every asset type has a writer |

## Build notes (smallest changes that kept a task's Verify meaningful)

- B1 (T02) The launcher calls Python outside any parenthesised block (`if not exist ... goto`).
  The pattern's `exit /b %ERRORLEVEL%` inside an `if (...)` block expands before Python runs
  and returns 0 for every exit code (reproduced; reported to the pattern's owner as a field
  report). The T03 launcher test asserts exit code 2 survives the launcher.
- B2 (T02) `--version` prints `f4forge <version>` as text (argparse convention); every command
  prints JSON. Usage errors are JSON with exit 2 instead of argparse text.
- B3 (T02) A `config` command shows and sets the three `config.json` keys, so Install.ps1 and
  users have one writer for `tools_root`, `workspace_root` and `game_root`.
- B4 (T03) `CHANGELOG.md`, `README.md`, the skill and `uabs-companion.json` start as short
  files so the mirror tests run from M0; T34, T35 and T37 complete them. The companion manifest
  carries a top-level `version` (the bundle reads only `schema`, `id` and `entry`).
- B5 (T04, T06) `ba2.read_header` and `plugin.read_header` exist from M1 so every installed
  fact has a command that re-reads it now (`game --archives`, `game --plugins`); T11 and T13
  extend those modules. The archive census writes its per-file list under the forge home.
- B6 (T04) An explicit game setting (argument, `FALLOUT4_ROOT`, config) that does not hold the
  game is a named failure and never falls through to Steam or registry detection.
- B7 (T04) The F4SE version is read from the DLL/loader version resource (`0.A.B.C` means F4SE
  A.B.C), with the `src/f4se-<ver>.tar.gz` name as a second witness.
- B8 (T06) `load_order.official_masters` is recorded `unverified` until T14 confirms the order.
- B9 (owner direction, 2026-11-15) The build runs every milestone to the end in one go instead of one
  milestone per session; each milestone is still committed with its evidence.
- B10 (T09) `.7z` assets are extracted with Windows' `tar.exe` (libarchive) first, then any
  7-Zip-compatible tool found by capability probe. The `7z` on this PC is a packaged fork whose
  view of `%LOCALAPPDATA%` is virtualised, so it is staged in the system temp folder.
- B11 (T09) xEdit 4.1.5f ships `xFOEdit64.exe` (no `xEdit64.exe`); FO4Edit64.exe is copied from it.
- B12 (T09, owner direction) Tool and framework pages stay in the data with their Nexus IDs, each
  checked against the public Nexus GraphQL v2 API (name lookup by ID); `f4forge nexus` exposes the
  same lookup to agents.
- B13 (T15) The worker targets net9.0, the lowest framework Mutagen.Bethesda.Fallout4 0.54.4 ships
  for (net9.0, net10.0) with an installed runtime. It writes through a temp folder that keeps the
  plugin's file name because Mutagen checks the name against the ModKey.
- B14 (T12) The DX10 chunk rule is "own chunk while the mip has at least 512x512 pixels, at most 4
  chunks", which matches every vanilla entry and Archive2's own defaults.
