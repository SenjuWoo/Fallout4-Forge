# Changelog

## 0.1.0 - 2026-11-15

First release.

- CLI `f4forge` with JSON on every command, exit codes 0/1/2/3, `--pretty`, an invocation log, `capabilities`
  generated from the parser, and `selftest`.
- Game discovery (Steam, registry, GOG): runtime and generation from the PE version resource, F4SE and Address
  Library match, official masters, Creation Club, Creation Kit tier, frameworks, mod managers, My Games.
- `doctor` in five sections; knowledge base of tiered facts, 28 topics, 21 frameworks with verified Nexus IDs,
  24 routes and `plan`.
- Pinned tool set in `tools.lock.json` (xEdit, Spriggit, Champollion, Caprica, DirectXTex, PyNifly, NifSkope,
  LOOT, CMT, CLASSIC, CKPE, CommonLibF4 and its template, F4SE source) with SHA-256 verification and a receipt.
- BA2 reader and writer (GNRL and DX10, versions 1/7/8) matching vanilla hashing and chunk layout, cross-checked
  with Archive2.
- Plugin walker, light-plugin rule from xEdit, load order, a Mutagen records worker (find, show, override, new,
  conflicts, validate, overlap, index) and Spriggit YAML export/build.
- Papyrus source cache (official or decompiled), PEX reader, compile with the official compiler or Caprica
  behind one diagnostics format, decompile.
- Textures (texconv presets by role), BGSM/BGEM byte-exact JSON round trip, NIF header and reference checks,
  Blender import/export through PyNifly, FUZ/XWM/LIP voice files.
- MCM, RobCo Patcher, Base Object Swapper, LooksMenu, BodySlide and INI validators; native F4SE plugin
  scaffold/build/export check; log and crash triage; Creation Kit precombine/previs/facegen wrappers and CKPE
  deployment, all dry run until approved.
- Projects with 12 kinds, `build`, `check` with evidence tiers, deterministic `package` with optional BA2 and
  FOMOD, `validate`, `deploy`/`undeploy` with receipts, `bump`, `index`, `conflicts`, Nexus lookups and page kit.
- Windows installer and uninstaller, agent skill `fallout4-forge`, companion manifest for the AI starter bundle.
