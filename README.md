# Fallout 4 Forge

A local-first toolkit for making, checking, packaging and shipping Fallout 4 mods. One CLI, `f4forge`,
prints JSON for every command, so people and AI agents can drive it the same way. Facts come from your
installed game; tools come from a pinned, hash-checked tool set.

## What it covers

| Area | Commands |
|---|---|
| Health and routing | `doctor`, `game`, `plan "<request>"`, `knowledge <topic>`, `facts`, `capabilities`, `selftest` |
| Projects | `new <Name> --kind ...`, `templates`, `build`, `check`, `package`, `validate`, `deploy`, `undeploy`, `bump` |
| Plugins and records | `plugin inspect\|esl-check\|export\|build`, `records find\|show\|override\|new\|conflicts\|validate`, `loadorder`, `index`, `conflicts` |
| Papyrus | `papyrus sources build`, `papyrus compile` (official compiler or Caprica), `papyrus decompile`, `papyrus pex` |
| Archives and assets | `ba2 list\|extract\|verify\|pack`, `tex inspect\|convert`, `material show\|build\|verify`, `nif info\|refs`, `mesh import\|export\|roundtrip`, `audio voice\|encode\|lip\|fuz\|unfuz` |
| Frameworks | `mcm`, `validate-config` (RobCo Patcher, Base Object Swapper, LooksMenu, BodySlide, INI), `native new\|build\|check` (CommonLibF4) |
| Creation Kit | `ck info\|precombine\|previs\|facegen\|ckpe-install` (dry run until `--approve`) |
| Logs and Nexus | `logs`, `explain "<error>"`, `nexus mod <id>`, `nexus find <name>`, `nexus page` |
| Tools | `tools status`, `tools sync --approve` |

Project kinds: plugin, papyrus, mcm, robco, bos, f4se, textures, materials, mesh, looksmenu, bodyslide, audio.

## Install (Windows)

Requirements: Windows, Python 3.10+, Fallout 4. Optional: the Fallout 4 Creation Kit (official compiler,
Archive2, voice tools), the .NET 9+ SDK (records worker), Blender (meshes), xmake and MSVC (native plugins).

1. Download the source zip from the latest release and extract it next to your other modding tools.
2. Run `START-HERE.bat` (or `Install.ps1 -ToolsRoot <folder> -WorkspaceRoot <folder>`). It creates a virtual
   environment, installs the forge, runs the tests, adds `f4forge` to your user PATH, copies the agent skill
   into the AI tools it finds, and syncs the pinned tools into the tools folder.
3. Open a new terminal and run `f4forge doctor`.

`Uninstall.ps1` removes the launcher, the PATH entry and the skill copies.

## Quick start

```bat
f4forge doctor
f4forge plan "add a new weapon mod with an MCM menu"
f4forge new "My Mod" --kind plugin --kind papyrus --kind mcm
cd "My Mod"
f4forge records new --type QUST --edid MyModQuest
f4forge build
f4forge check
f4forge package
f4forge deploy            # dry run; add --approve to copy into the game
```

## Safety

- The game folder, mod-manager staging, saves and INIs are read-only. Only `deploy` and `ck` write into the
  game, each a dry run until `--approve`, with a receipt, backups and an undo.
- Tools are downloaded only by `tools sync --approve`, verified by SHA-256 before extraction, into one tools
  folder that the forge owns through a receipt.
- Packages are scanned for private paths and API keys.

## Evidence tiers

Results name the tier they reached: static (check), compile, package. Loading in game and gameplay are never
claimed by the forge. Every fact in `knowledge/facts.json` names its tier (installed, primary, secondary,
unverified) and source; unverified facts are never enforced.

## Known gaps in 0.1

- Animation (HKX) and interface (SWF) are knowledge-only.
- Voice generation and precombine/previs runs need the Creation Kit.
- Archives written by the forge pass static and cross-tool checks; in-game loading is not tested by the forge.

## Licence

MIT (see `LICENSE`). Third-party tools keep their own licences (`THIRD-PARTY.md`). Fallout 4 and the
Creation Kit belong to Bethesda Softworks; this project is not affiliated with them.
