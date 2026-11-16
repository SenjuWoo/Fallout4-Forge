---
name: fallout4-forge
description: Make, check, package and ship Fallout 4 mods with the f4forge CLI - plugins and records, Papyrus, F4SE native plugins, BA2 archives, textures, BGSM materials, NIF meshes, voice files, MCM menus, RobCo Patcher, Base Object Swapper, LooksMenu, BodySlide, FOMOD, Nexus pages, crash logs. Use for any Fallout 4 modding request.
---

# Fallout 4 Forge

Version: 0.1.1

Every command prints JSON. Exit 0 ok, 1 findings, 2 named failure (read `fix`), 3 forge bug.

## Cold start

1. `f4forge doctor` - toolchain, game (runtime, F4SE, Creation Kit tier), payload, tools, records worker.
2. `f4forge plan "<what the user wants>"` - routes, commands in order, knowledge topics, tools, what to avoid, gaps.
3. `f4forge knowledge <topic>` - short rules, each tagged with the fact behind it (`f4forge facts <word>`).
4. `f4forge capabilities` - every command and argument.

## Make a mod

- `f4forge new "<Name>" --kind plugin --kind papyrus --kind mcm ...` (kinds: `f4forge templates`). Projects go to the workspace root.
- Records: `f4forge records find --index --edid <text>`, `records new --type MISC --edid X`, `records override <FormKey>`.
  The project's plugin/ YAML tree is the source of truth; `records` refreshes it.
- `f4forge build` (plugin, scripts, materials, textures, voice) -> `f4forge check` -> `f4forge package` -> `f4forge validate <zip>`.
- Assets: `tex convert|inspect`, `material show|build`, `nif info|refs`, `mesh import|export`, `audio voice|encode|lip`, `ba2 pack|list`.
- Frameworks: `mcm <folder>`, `validate-config <ini|json|xml>`, `native new|build`.
- Look things up: `nexus mod <id>`, `nexus find <name>`, `loadorder`, `conflicts`, `logs`, `explain "<error>"`, `game`.

## Boundaries

- The game folder, Data, Vortex/MO2 staging, saves and INIs are read-only inputs.
- Only `f4forge deploy` and `f4forge ck ...` write into the game, each a dry run until `--approve`, with a receipt.
- Never edit Fallout4.esm or DLC masters. Never ship PLAN/STATE/CHANGELOG, f4forge.json or script sources outside Scripts/Source.
- Tools come from `tools.lock.json` (`f4forge tools status|sync`); nothing is installed globally.

## Evidence

Report the tier reached: static (check), compile, package; load and gameplay are NOT RUN until someone tests in game.
Facts carry tiers: installed (read here), primary (official source with commit), secondary, unverified (never enforced).
Animation (HKX) and interface (SWF) are knowledge-only in 0.1; voice and previs need the Creation Kit tier.
