# AGENTS - Fallout 4 Forge

Instructions for agents working on this repository (the forge itself, not mods made with it).

## Sources of truth

- `PLAN.md` - the work order (tasks, verifies, evidence); `STATE.md` - progress, gaps, next action.
- `DECISIONS.md` - settled decisions (D1-D15) and build notes (B*); do not reopen them.
- `src/f4forge/__init__.py` owns the version; CHANGELOG.md, STATE.md, the skill and `uabs-companion.json` mirror it (tests check).
- `src/f4forge/knowledge/facts.json` - every game, format or framework fact with tier, source and the command that re-reads it.
- `tools.lock.json` - pinned tools with SHA-256 (release assets) or commits (clones).
- Machine detail lives only in the git-ignored `LOCAL.md`; tracked files carry no drive letters or user paths (hygiene test).

## Where the logic lives

| Area | Module |
|---|---|
| CLI, JSON contract, exit codes | `cli.py`, `util.py`, `home.py` |
| Game discovery, health | `game.py`, `pe.py`, `doctor.py` |
| Knowledge, routing | `knowledge.py`, `knowledge/*.json`, `knowledge/*.md` |
| Tools | `tools.py`, `tools.lock.json` |
| Archives, plugins, load order | `ba2.py`, `dds.py`, `plugin.py`, `loadorder.py` |
| Records (.NET worker), YAML tree | `records.py`, `workers/F4Forge.Records/`, `spriggit.py`, `index.py` |
| Papyrus | `papyrus.py` (+ `tests/fixtures/psc-stubs`) |
| Assets | `textures.py`, `bgsm.py`, `nif.py`, `blender_nif.py`, `audio.py` |
| Framework configs, data kinds | `mcm.py`, `frameworks_cfg.py`, `datakinds.py` |
| Native, logs, Creation Kit | `native.py`, `logs.py`, `ck.py` |
| Projects, check, release | `project.py`, `templates/`, `check.py`, `package.py`, `fomod.py`, `deploy.py`, `nexus.py` |

## Loop

1. Read STATE.md; run `f4forge doctor` and `f4forge game`.
2. Change code with a test (`tests/test_f4forge.py`, synthetic fixtures only - never a game file).
3. `python tests/run_tests.py`, `f4forge selftest`, then the task's verify on the installed game; record counts and hashes, not pasted output.
4. Update PLAN.md evidence and STATE.md; commit with the operator's identity, no AI attribution line.

## Boundaries

- The game folder, Data, mod-manager staging, saves and INIs are read-only. Only `deploy` and `ck` write into the game, dry run until `--approve`.
- A new fact enters facts.json only with a tier and a source; `unverified` facts are never enforced.
- Other forges are read-only; a defect found in one is filed with the bundle's `field_report.py`.
